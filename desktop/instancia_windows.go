package main

import (
	"errors"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

var (
	trava                   windows.Handle
	procFindWindowW         = user32.NewProc("FindWindowW")
	procSetForegroundWindow = user32.NewProc("SetForegroundWindow")
	procIsIconic            = user32.NewProc("IsIconic")
)

func instanciaUnica() bool {
	h, err := windows.CreateMutex(nil, false, windows.StringToUTF16Ptr(`Local\Apogeu`))
	if errors.Is(err, windows.ERROR_ALREADY_EXISTS) {
		if h != 0 {
			windows.CloseHandle(h)
		}
		return false
	}
	trava = h
	return true
}

func focarJanelaAberta() {
	classe := windows.StringToUTF16Ptr("webview")
	titulo := windows.StringToUTF16Ptr(nomeApp)
	for tentativa := 0; tentativa < 20; tentativa++ {
		h, _, _ := procFindWindowW.Call(uintptr(unsafe.Pointer(classe)), uintptr(unsafe.Pointer(titulo)))
		if h != 0 {
			if minimizada, _, _ := procIsIconic.Call(h); minimizada != 0 {
				procShowWindow.Call(h, swRestore)
			}
			procSetForegroundWindow.Call(h)
			return
		}
		time.Sleep(150 * time.Millisecond)
	}
}
