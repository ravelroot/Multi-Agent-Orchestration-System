package main

import (
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

const (
	createNewConsole = 0x00000010
	createNoWindow   = 0x08000000
)

var grupo windows.Handle

func caminhoPython() []string {
	return []string{".venv", "Scripts", "python.exe"}
}

func ocultarJanela(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
}

func comandoPreparar(raiz string) *exec.Cmd {
	interpretador := os.Getenv("ComSpec")
	if interpretador == "" {
		interpretador = filepath.Join(os.Getenv("SystemRoot"), "System32", "cmd.exe")
	}
	cmd := exec.Command(interpretador)
	cmd.Dir = raiz
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CmdLine:       syscall.EscapeArg(interpretador) + ` /d /c "title Apogeu - preparação & call iniciar.cmd preparar"`,
		CreationFlags: createNewConsole,
	}
	return cmd
}

func criarGrupoDeProcessos() {
	h, err := windows.CreateJobObject(nil, nil)
	if err != nil {
		return
	}
	info := windows.JOBOBJECT_EXTENDED_LIMIT_INFORMATION{
		BasicLimitInformation: windows.JOBOBJECT_BASIC_LIMIT_INFORMATION{
			LimitFlags: windows.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
		},
	}
	if _, err := windows.SetInformationJobObject(h, windows.JobObjectExtendedLimitInformation, uintptr(unsafe.Pointer(&info)), uint32(unsafe.Sizeof(info))); err != nil {
		windows.CloseHandle(h)
		return
	}
	grupo = h
}

func vincularAoGrupo(pid int) {
	if grupo == 0 {
		return
	}
	processo, err := windows.OpenProcess(windows.PROCESS_SET_QUOTA|windows.PROCESS_TERMINATE, false, uint32(pid))
	if err != nil {
		return
	}
	defer windows.CloseHandle(processo)
	_ = windows.AssignProcessToJobObject(grupo, processo)
}

func fecharGrupoDeProcessos() {
	if grupo != 0 {
		windows.CloseHandle(grupo)
		grupo = 0
	}
}

func abrirNoNavegador(endereco string) {
	u, err := url.Parse(endereco)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" {
		return
	}
	executar(u.String())
}

func abrirArquivo(caminho string) {
	if _, err := os.Stat(caminho); err != nil {
		return
	}
	executar(caminho)
}

func executar(alvo string) {
	_ = windows.ShellExecute(0, windows.StringToUTF16Ptr("open"), windows.StringToUTF16Ptr(alvo), nil, nil, windows.SW_SHOWNORMAL)
}
