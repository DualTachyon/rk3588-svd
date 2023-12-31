TARGET = rk3588.svd
DEFS = $(wildcard def/*.def) $(wildcard def/*/*.def)

ifeq ($(EMPTY),1)
FLAGS = --empty
else
FLAGS :=
endif

all: $(TARGET)

$(TARGET): $(DEFS)
	./convert-def.py --svd $(FLAGS) -o $@ -i $^
	xmllint --schema CMSIS-SVD.xsd --noout $@

clean:
	rm -f $(TARGET)

