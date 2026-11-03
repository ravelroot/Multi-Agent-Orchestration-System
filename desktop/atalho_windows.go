package main

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	ole32                = windows.NewLazySystemDLL("ole32.dll")
	procCoCreateInstance = ole32.NewProc("CoCreateInstance")
)

const (
	clsctxInprocServer = 0x1
	coinitApartment    = 0x2

	metodoRelease        = 2
	metodoQueryInterface = 0
	shellLinkSetDesc     = 7
	shellLinkSetWorkDir  = 9
	shellLinkSetIcon     = 17
	shellLinkSetPath     = 20
	persistFileSave      = 6

	registroDoAtalho = "atalho.txt"
)

func registrarNoMenuIniciar(pastaDados string) {
	exe, err := os.Executable()
	if err != nil {
		return
	}
	if resolvido, err := filepath.EvalSymlinks(exe); err == nil {
		exe = resolvido
	}
	programas, err := windows.KnownFolderPath(windows.FOLDERID_Programs, 0)
	if err != nil {
		return
	}
	atalho := filepath.Join(programas, nomeApp+".lnk")
	registro := filepath.Join(pastaDados, registroDoAtalho)
	anterior, _ := os.ReadFile(registro)
	mesmoLugar := strings.EqualFold(strings.TrimSpace(string(anterior)), exe)
	if mesmoLugar {
		return
	}
	if criarAtalho(atalho, exe) {
		_ = os.WriteFile(registro, []byte(exe), 0o644)
	}
}

func criarAtalho(destino, exe string) bool {
	_ = windows.CoInitializeEx(0, coinitApartment)
	clsidShellLink, _ := windows.GUIDFromString("{00021401-0000-0000-C000-000000000046}")
	iidShellLink, _ := windows.GUIDFromString("{000214F9-0000-0000-C000-000000000046}")
	iidPersistFile, _ := windows.GUIDFromString("{0000010B-0000-0000-C000-000000000046}")

	var link unsafe.Pointer
	r, _, _ := procCoCreateInstance.Call(uintptr(unsafe.Pointer(&clsidShellLink)), 0, clsctxInprocServer,
		uintptr(unsafe.Pointer(&iidShellLink)), uintptr(unsafe.Pointer(&link)))
	if r != 0 || link == nil {
		return false
	}
	defer chamar(link, metodoRelease)

	caminho, _ := windows.UTF16PtrFromString(exe)
	pasta, _ := windows.UTF16PtrFromString(filepath.Dir(exe))
	descricao, _ := windows.UTF16PtrFromString("Apogeu, orquestrador de agentes de IA")
	arquivo, _ := windows.UTF16PtrFromString(destino)
	defer runtime.KeepAlive([]*uint16{caminho, pasta, descricao, arquivo})

	chamar(link, shellLinkSetPath, uintptr(unsafe.Pointer(caminho)))
	chamar(link, shellLinkSetWorkDir, uintptr(unsafe.Pointer(pasta)))
	chamar(link, shellLinkSetDesc, uintptr(unsafe.Pointer(descricao)))
	chamar(link, shellLinkSetIcon, uintptr(unsafe.Pointer(caminho)), 0)

	var persistente unsafe.Pointer
	if chamar(link, metodoQueryInterface, uintptr(unsafe.Pointer(&iidPersistFile)), uintptr(unsafe.Pointer(&persistente))) != 0 || persistente == nil {
		return false
	}
	defer chamar(persistente, metodoRelease)
	return chamar(persistente, persistFileSave, uintptr(unsafe.Pointer(arquivo)), 1) == 0
}

func chamar(objeto unsafe.Pointer, indice uintptr, argumentos ...uintptr) uintptr {
	tabela := *(*unsafe.Pointer)(objeto)
	metodo := *(*uintptr)(unsafe.Add(tabela, indice*unsafe.Sizeof(uintptr(0))))
	r, _, _ := syscall.SyscallN(metodo, append([]uintptr{uintptr(objeto)}, argumentos...)...)
	return r
}
