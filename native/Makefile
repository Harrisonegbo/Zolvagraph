# Zolvagraph native scan engine
CC ?= gcc
CFLAGS ?= -O3 -fPIC -Wall
LIB = libzolvagraph_scan.so
DLL = zolvagraph_scan.dll

all: $(LIB)

$(LIB): scan_engine.c
	$(CC) $(CFLAGS) -shared -o $@ scan_engine.c

windows:
	$(CC) -O3 -shared -o $(DLL) scan_engine.c

clean:
	rm -f $(LIB) $(DLL)

.PHONY: all windows clean
