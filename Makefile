TARGET = rk3588.svd
DEFS = $(wildcard def/*.def) $(wildcard def/*/*.def)

all: $(TARGET)

$(TARGET): $(DEFS)
	./convert-def.py -o $@ -i $^

clean:
	rm -f $(TARGET)

