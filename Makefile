TARGET = rk3588.svd
DEFS = $(wildcard def/*.def) $(wildcard def/*/*.def)

all: $(TARGET)

$(TARGET): $(DEFS)
	./convert-def.py -o $@ -i $^
	xmllint --schema CMSIS-SVD.xsd --noout $@

clean:
	rm -f $(TARGET)

