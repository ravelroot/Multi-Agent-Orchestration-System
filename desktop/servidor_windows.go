package main

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

const (
	portaPadrao       = 8000
	limiteInicio      = 2 * time.Minute
	linhasDoRegistro  = 30
	urlPython         = "https://www.python.org/downloads/"
	urlNode           = "https://nodejs.org/"
	textoPreparando   = "Na primeira abertura, o Apogeu cria o ambiente do Python, instala as dependências e compila a interface. Acompanhe na janela do console; isso leva alguns minutos e só acontece de novo quando a versão mudar."
	textoIniciando    = "Iniciando o servidor local."
	textoConsoleParou = "A preparação parou antes de terminar. Veja a mensagem na janela do console, corrija o problema e clique em Tentar de novo."
)

type etapa struct {
	titulo      string
	texto       string
	detalhe     string
	ajuda       string
	ajudaRotulo string
	carregando  bool
	erro        bool
	registro    bool
	endereco    string
}

type execucao struct {
	cmd    *exec.Cmd
	fim    chan struct{}
	parada atomic.Bool
}

type servidor struct {
	raiz     string
	mu       sync.Mutex
	atual    *execucao
	ocupado  atomic.Bool
	fechando atomic.Bool
}

func novoServidor(raiz string) *servidor {
	criarGrupoDeProcessos()
	return &servidor{raiz: raiz}
}

func (s *servidor) caminho(partes ...string) string {
	return filepath.Join(append([]string{s.raiz}, partes...)...)
}

func (s *servidor) registro() string {
	return s.caminho("data", "apogeu.log")
}

func existe(caminho string) bool {
	_, err := os.Stat(caminho)
	return err == nil
}

func lerTexto(caminho string) string {
	dados, err := os.ReadFile(caminho)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(strings.TrimPrefix(string(dados), "\ufeff"))
}

func (s *servidor) faltando(rigoroso bool) etapa {
	if !existe(s.caminho(caminhoPython()...)) || !existe(s.caminho(".venv", ".instalado")) {
		return etapa{
			titulo:      "O ambiente do Python não ficou pronto",
			texto:       "Confira se o Python 3.11 ou mais recente está instalado e marcado para entrar no PATH, e clique em Tentar de novo.",
			ajuda:       urlPython,
			ajudaRotulo: "Baixar o Python",
			erro:        true,
		}
	}
	interfacePronta := existe(s.caminho("frontend", "out", "index.html"))
	if rigoroso && interfacePronta {
		versao := lerTexto(s.caminho("VERSION"))
		interfacePronta = versao != "" && lerTexto(s.caminho("frontend", "out", ".versao")) == versao
	}
	if !interfacePronta {
		return etapa{
			titulo:      "A interface não foi compilada",
			texto:       "Para compilar a interface na primeira abertura, o Apogeu precisa do Node.js 20.9 ou mais recente. Instale e clique em Tentar de novo.",
			ajuda:       urlNode,
			ajudaRotulo: "Baixar o Node.js",
			erro:        true,
		}
	}
	return etapa{}
}

func (s *servidor) abrir(avisar func(etapa)) {
	if !s.ocupado.CompareAndSwap(false, true) {
		return
	}
	defer s.ocupado.Store(false)
	s.parar()

	if s.faltando(true).erro {
		avisar(etapa{titulo: "Preparando o Apogeu", texto: textoPreparando, carregando: true})
		if err := s.preparar(); err != nil {
			avisar(etapa{titulo: "A preparação não terminou", texto: textoConsoleParou, erro: true})
			return
		}
		if falta := s.faltando(false); falta.erro {
			avisar(falta)
			return
		}
	}
	if s.fechando.Load() {
		return
	}

	avisar(etapa{titulo: "Abrindo o Apogeu", texto: textoIniciando, carregando: true})
	porta, existente := s.escolherPorta()
	endereco := fmt.Sprintf("http://127.0.0.1:%d/", porta)
	if existente {
		avisar(etapa{endereco: endereco})
		return
	}
	e, err := s.subir(porta)
	if err != nil {
		avisar(etapa{titulo: "Não foi possível iniciar o servidor", texto: err.Error(), erro: true})
		return
	}
	if err := esperar(porta, e.fim, limiteInicio); err != nil {
		e.parada.Store(true)
		s.parar()
		avisar(etapa{titulo: "O servidor do Apogeu não abriu", texto: err.Error(), detalhe: s.ultimasLinhas(), erro: true, registro: true})
		return
	}
	avisar(etapa{endereco: endereco})
	go func() {
		<-e.fim
		if !e.parada.Load() && !s.fechando.Load() {
			avisar(etapa{titulo: "O servidor do Apogeu parou", texto: "O servidor local fechou sozinho. Veja as últimas linhas do registro e clique em Tentar de novo.", detalhe: s.ultimasLinhas(), erro: true, registro: true})
		}
	}()
}

func (s *servidor) preparar() error {
	cmd := comandoPreparar(s.raiz)
	if err := cmd.Start(); err != nil {
		return err
	}
	vincularAoGrupo(cmd.Process.Pid)
	return cmd.Wait()
}

func (s *servidor) escolherPorta() (int, bool) {
	porta := portaConfigurada(s.caminho(".env"))
	if ehApogeu(porta) {
		return porta, true
	}
	if portaLivre(porta) {
		return porta, false
	}
	return portaQualquer(porta), false
}

func portaConfigurada(arquivoEnv string) int {
	if p, err := strconv.Atoi(strings.TrimSpace(os.Getenv("APOGEU_PORT"))); err == nil && p > 0 && p < 65536 {
		return p
	}
	arquivo, err := os.Open(arquivoEnv)
	if err != nil {
		return portaPadrao
	}
	defer arquivo.Close()
	porta := portaPadrao
	linhas := bufio.NewScanner(arquivo)
	for linhas.Scan() {
		chave, valor, ok := strings.Cut(strings.TrimSpace(linhas.Text()), "=")
		if !ok || !strings.EqualFold(strings.TrimSpace(strings.TrimPrefix(strings.TrimPrefix(chave, "\ufeff"), "export ")), "APOGEU_PORT") {
			continue
		}
		valor = strings.Trim(strings.TrimSpace(valor), `"'`)
		if p, err := strconv.Atoi(valor); err == nil && p > 0 && p < 65536 {
			porta = p
		}
	}
	return porta
}

func ehApogeu(porta int) bool {
	cliente := &http.Client{Timeout: 1500 * time.Millisecond}
	resposta, err := cliente.Get(fmt.Sprintf("http://127.0.0.1:%d/api/saude", porta))
	if err != nil {
		return false
	}
	defer resposta.Body.Close()
	if resposta.StatusCode != http.StatusOK {
		return false
	}
	var saude struct {
		Versao   string          `json:"versao"`
		Provedor json.RawMessage `json:"provedor"`
	}
	if json.NewDecoder(io.LimitReader(resposta.Body, 1<<16)).Decode(&saude) != nil {
		return false
	}
	return saude.Versao != "" && len(saude.Provedor) > 0
}

func portaLivre(porta int) bool {
	ouvinte, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", porta))
	if err != nil {
		return false
	}
	ouvinte.Close()
	return true
}

func portaQualquer(reserva int) int {
	ouvinte, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return reserva
	}
	defer ouvinte.Close()
	return ouvinte.Addr().(*net.TCPAddr).Port
}

func (s *servidor) subir(porta int) (*execucao, error) {
	if err := os.MkdirAll(filepath.Dir(s.registro()), 0o755); err != nil {
		return nil, err
	}
	registro, err := os.Create(s.registro())
	if err != nil {
		return nil, err
	}
	cmd := exec.Command(s.caminho(caminhoPython()...), "-m", "apogeu")
	cmd.Dir = s.raiz
	cmd.Env = append(os.Environ(),
		"APOGEU_HOST=127.0.0.1",
		"APOGEU_PORT="+strconv.Itoa(porta),
		"PYTHONUNBUFFERED=1",
		"PYTHONIOENCODING=utf-8",
	)
	cmd.Stdout = registro
	cmd.Stderr = registro
	ocultarJanela(cmd)
	if err := cmd.Start(); err != nil {
		registro.Close()
		return nil, err
	}
	vincularAoGrupo(cmd.Process.Pid)
	e := &execucao{cmd: cmd, fim: make(chan struct{})}
	go func() {
		_ = cmd.Wait()
		registro.Close()
		close(e.fim)
	}()
	s.mu.Lock()
	s.atual = e
	s.mu.Unlock()
	return e, nil
}

func esperar(porta int, fim <-chan struct{}, limite time.Duration) error {
	cliente := &http.Client{Timeout: time.Second}
	endereco := fmt.Sprintf("http://127.0.0.1:%d/api/saude", porta)
	prazo := time.After(limite)
	for {
		if resposta, err := cliente.Get(endereco); err == nil {
			resposta.Body.Close()
			return nil
		}
		select {
		case <-fim:
			return errors.New("O servidor fechou logo ao iniciar. Veja as últimas linhas do registro abaixo.")
		case <-prazo:
			return fmt.Errorf("O servidor não respondeu em %d minutos. Veja as últimas linhas do registro abaixo.", int(limite.Minutes()))
		case <-time.After(300 * time.Millisecond):
		}
	}
}

func (s *servidor) parar() {
	s.mu.Lock()
	e := s.atual
	s.atual = nil
	s.mu.Unlock()
	if e == nil {
		return
	}
	e.parada.Store(true)
	select {
	case <-e.fim:
		return
	default:
	}
	_ = e.cmd.Process.Kill()
	select {
	case <-e.fim:
	case <-time.After(5 * time.Second):
	}
}

func (s *servidor) encerrar() {
	s.fechando.Store(true)
	s.parar()
	fecharGrupoDeProcessos()
}

func (s *servidor) ultimasLinhas() string {
	arquivo, err := os.Open(s.registro())
	if err != nil {
		return ""
	}
	defer arquivo.Close()
	if info, err := arquivo.Stat(); err == nil && info.Size() > 16<<10 {
		_, _ = arquivo.Seek(-16<<10, io.SeekEnd)
	}
	dados, _ := io.ReadAll(arquivo)
	linhas := strings.Split(strings.TrimRight(strings.ReplaceAll(string(dados), "\r\n", "\n"), "\n"), "\n")
	if len(linhas) > linhasDoRegistro {
		linhas = linhas[len(linhas)-linhasDoRegistro:]
	}
	return strings.Join(linhas, "\n")
}
