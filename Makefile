TARGET = rk3588.svd
DEFS = $(wildcard *.def) $(wildcard */*.def)

all: $(TARGET)

$(TARGET): $(DEFS)
	./def2svd.py -o $@ -i $^

clean:
	rm -f $(TARGET)

