package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"runtime"
	"strconv"
	"sync"
)

// held keeps allocated memory alive so the GC cannot reclaim it.
var (
	held   [][]byte
	heldMu sync.Mutex
)

func main() {
	addr := ":8080"
	if v := os.Getenv("PORT"); v != "" {
		addr = ":" + v
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", handleHealth)
	mux.HandleFunc("/eat", handleEat)
	mux.HandleFunc("/burn", handleBurn)

	log.Printf("api listening on %s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok\n"))
}

func handleEat(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	mbStr := r.URL.Query().Get("mb")
	if mbStr == "" {
		http.Error(w, "missing query param mb", http.StatusBadRequest)
		return
	}
	mb, err := strconv.Atoi(mbStr)
	if err != nil || mb < 0 {
		http.Error(w, "mb must be a non-negative integer", http.StatusBadRequest)
		return
	}

	buf := make([]byte, mb*1024*1024)
	// Touch pages so RSS actually grows (not just virtual size).
	for i := 0; i < len(buf); i += 4096 {
		buf[i] = 1
	}
	heldMu.Lock()
	held = append(held, buf)
	heldMu.Unlock()

	w.WriteHeader(http.StatusOK)
	_, _ = fmt.Fprintf(w, "held %d MB (total chunks: %d)\n", mb, len(held))
}

func handleBurn(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	// Busy-loop on one OS thread so a single core is saturated.
	go func() {
		runtime.LockOSThread()
		for {
		}
	}()
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("burning one core\n"))
}
