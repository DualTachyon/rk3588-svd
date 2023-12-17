TARGET = rk3588.svd
DEFS = $(wildcard *.def) $(wildcard cru/*.def) $(wildcard grf/*.def)

all: $(TARGET)

$(TARGET): $(DEFS)
	./def2svd.py -o $@ -i $^

clean:
	rm -f $(TARGET)

