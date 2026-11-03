package main

import (
	"os"
	"path/filepath"
	"runtime"
	"unsafe"

	webview2 "github.com/jchv/go-webview2"
	"golang.org/x/sys/windows"
)

var versao = "dev"

const (
	nomeApp     = "Apogeu"
	idIcone     = 2
	urlWebView2 = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

	wmSetIcon            = 0x0080
	swMaximize           = 3
	swRestore            = 9
	iconeGrande          = 1
	iconePequeno         = 0
	imagemIcone          = 1
	smCxIcon             = 11
	smCyIcon             = 12
	smCxSmIcon           = 49
	smCySmIcon           = 50
	swpNoZOrder          = 0x0004
	swpNoOwnerZOrder     = 0x0200
	monitorDefaultToNear = 0x00000002
	mbYesNo              = 0x00000004
	mbIconWarning        = 0x00000030
	idYes                = 6
)

var (
	user32                = windows.NewLazySystemDLL("user32.dll")
	procSetWindowPos      = user32.NewProc("SetWindowPos")
	procMonitorFromWindow = user32.NewProc("MonitorFromWindow")
	procGetMonitorInfoW   = user32.NewProc("GetMonitorInfoW")
	procSendMessageW      = user32.NewProc("SendMessageW")
	procShowWindow        = user32.NewProc("ShowWindow")
	procLoadImageW        = user32.NewProc("LoadImageW")
	procGetSystemMetrics  = user32.NewProc("GetSystemMetrics")
	procGetDpiForWindow   = user32.NewProc("GetDpiForWindow")
	procGetSysMetricsDpi  = user32.NewProc("GetSystemMetricsForDpi")
)

type retangulo struct{ Left, Top, Right, Bottom int32 }

type infoMonitor struct {
	Size    uint32
	Monitor retangulo
	Work    retangulo
	Flags   uint32
}

type janela struct {
	w    webview2.WebView
	hwnd uintptr
	srv  *servidor
}

func init() {
	runtime.LockOSThread()
}

func main() {
	if !instanciaUnica() {
		focarJanelaAberta()
		return
	}
	raiz, err := pastaDoProjeto()
	if err != nil {
		avisar("Não foi possível localizar a pasta do Apogeu:\n\n" + err.Error())
		return
	}
	if _, err := os.Stat(filepath.Join(raiz, "apogeu", "__main__.py")); err != nil {
		avisar("O Apogeu.exe precisa ficar na pasta do projeto, ao lado da pasta apogeu e do iniciar.cmd.\n\nPasta atual:\n" + raiz)
		return
	}
	dados, err := pastaDeDados()
	if err != nil {
		avisar("Não foi possível preparar a pasta de dados do Apogeu:\n\n" + err.Error())
		return
	}
	registrarNoMenuIniciar(dados)

	w := webview2.NewWithOptions(webview2.WebViewOptions{
		AutoFocus: true,
		DataPath:  filepath.Join(dados, "WebView2"),
		WindowOptions: webview2.WindowOptions{
			Title:  nomeApp,
			Width:  1440,
			Height: 900,
			IconId: idIcone,
			Center: true,
		},
	})
	if w == nil {
		faltaWebView2()
		return
	}

	j := &janela{w: w, hwnd: uintptr(w.Window()), srv: novoServidor(raiz)}
	j.carregarIcones()
	j.centralizar()
	procShowWindow.Call(j.hwnd, swMaximize)

	precisa(w.Bind("__apogeuAbrirFora", abrirNoNavegador))
	precisa(w.Bind("__apogeuTentarDeNovo", func() { go j.abrir() }))
	precisa(w.Bind("__apogeuAbrirRegistro", func() { abrirArquivo(j.srv.registro()) }))
	w.Init(scriptJanela)
	w.SetHtml(paginaEspera(etapa{titulo: "Abrindo o Apogeu", texto: "Iniciando o servidor local.", carregando: true}))

	go j.abrir()
	w.Run()
	j.srv.encerrar()
}

func (j *janela) abrir() {
	j.srv.abrir(func(e etapa) {
		j.w.Dispatch(func() {
			if e.endereco != "" {
				j.w.Navigate(e.endereco)
				return
			}
			j.w.SetHtml(paginaEspera(e))
		})
	})
}

func pastaDoProjeto() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	if resolvido, err := filepath.EvalSymlinks(exe); err == nil {
		exe = resolvido
	}
	return filepath.Dir(exe), nil
}

func pastaDeDados() (string, error) {
	base, err := os.UserCacheDir()
	if err != nil {
		return "", err
	}
	pasta := filepath.Join(base, nomeApp)
	return pasta, os.MkdirAll(pasta, 0o755)
}

func (j *janela) carregarIcones() {
	var modulo windows.Handle
	if windows.GetModuleHandleEx(0, nil, &modulo) != nil {
		return
	}
	medida := func(indice uintptr) uintptr {
		if procGetDpiForWindow.Find() == nil && procGetSysMetricsDpi.Find() == nil {
			if dpi, _, _ := procGetDpiForWindow.Call(j.hwnd); dpi != 0 {
				v, _, _ := procGetSysMetricsDpi.Call(indice, dpi)
				return v
			}
		}
		v, _, _ := procGetSystemMetrics.Call(indice)
		return v
	}
	for _, icone := range []struct{ tipo, largura, altura uintptr }{
		{iconeGrande, smCxIcon, smCyIcon},
		{iconePequeno, smCxSmIcon, smCySmIcon},
	} {
		h, _, _ := procLoadImageW.Call(uintptr(modulo), idIcone, imagemIcone, medida(icone.largura), medida(icone.altura), 0)
		if h != 0 {
			procSendMessageW.Call(j.hwnd, wmSetIcon, icone.tipo, h)
		}
	}
}

func (j *janela) centralizar() {
	m := infoMonitor{Size: uint32(unsafe.Sizeof(infoMonitor{}))}
	h, _, _ := procMonitorFromWindow.Call(j.hwnd, monitorDefaultToNear)
	if ok, _, _ := procGetMonitorInfoW.Call(h, uintptr(unsafe.Pointer(&m))); ok == 0 {
		return
	}
	area := m.Work
	largura := (area.Right - area.Left) * 85 / 100
	altura := (area.Bottom - area.Top) * 85 / 100
	x := area.Left + (area.Right-area.Left-largura)/2
	y := area.Top + (area.Bottom-area.Top-altura)/2
	procSetWindowPos.Call(j.hwnd, 0, uintptr(x), uintptr(y), uintptr(largura), uintptr(altura), swpNoZOrder|swpNoOwnerZOrder)
}

func faltaWebView2() {
	texto := "O Apogeu precisa do Microsoft Edge WebView2 Runtime, que já vem no Windows 10 e 11 atualizados.\n\n" +
		"Quer abrir a página de download da Microsoft agora? Depois de instalar, abra o Apogeu de novo."
	if caixaDeMensagem(texto, mbYesNo|mbIconWarning) == idYes {
		abrirNoNavegador(urlWebView2)
	}
}

func avisar(texto string) { caixaDeMensagem(texto, mbIconWarning) }

func caixaDeMensagem(texto string, opcoes uint32) int32 {
	r, _ := windows.MessageBox(0, windows.StringToUTF16Ptr(texto), windows.StringToUTF16Ptr(nomeApp), opcoes)
	return r
}

func precisa(err error) {
	if err != nil {
		avisar("Erro ao preparar o Apogeu: " + err.Error())
		os.Exit(1)
	}
}
