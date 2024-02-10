TARGET = rk3588.svd
DEFS = $(wildcard def/*.def) $(wildcard def/*/*.def) $(wildcard def/*/*/*.def)

ifeq ($(EMPTY),1)
FLAGS = --empty
else
FLAGS :=
endif

all: $(TARGET)

$(TARGET): $(DEFS)
	./convert-def.py --headers -o include -i $^
	rsync --delete -r include pi-nas:/home/www/html/files/RockChip/include
	./convert-def.py --svd $(FLAGS) -o $@ -i $^
	xmllint --schema CMSIS-SVD.xsd --noout $@

clean:
	rm -f $(TARGET)
	rm -rf include/*

