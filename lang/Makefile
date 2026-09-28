.DEFAULT_GOAL := all
PO_DIR := ./po
MO_DIR := ./mo

ifndef LANGUAGES
	PO := $(patsubst $(PO_DIR)/%,%,$(patsubst %.po,%,$(wildcard $(PO_DIR)/*.po)))
else
	ifeq ($(LANGUAGES), all)
		PO := $(patsubst $(PO_DIR)/%,%,$(patsubst %.po,%,$(wildcard $(PO_DIR)/*.po)))
	else
		PO := $(LANGUAGES)
	endif
endif

# An explicitly selected language may have only a maintained supplement in the
# source checkout.  Reuse any pinned base MO, and never invent a missing base PO.
PO := $(foreach language,$(PO),$(if $(wildcard $(PO_DIR)/$(language).po $(MO_DIR)/$(language)/LC_MESSAGES/cataclysm-dda.mo),$(language),$(if $(wildcard ./cph/$(language).po),,$(language))))
MO := $(patsubst %,$(MO_DIR)/%/LC_MESSAGES/cataclysm-dda.mo,$(PO))
CPH_PO := $(wildcard ./cph/*.po)
CPH_MO := $(patsubst ./cph/%.po,$(MO_DIR)/cph/%/LC_MESSAGES/cataclysm-dda.mo,$(CPH_PO))

clean clean-plan: export CPH_CLEAN_PO_DIR = $(PO_DIR)
clean clean-plan: export CPH_CLEAN_MO_DIR = $(MO_DIR)
clean clean-plan: export CPH_CLEAN_LANGUAGES = $(LANGUAGES)

# Only locally generated, unchanged outputs with a matching PO receipt qualify.
# Downloaded/locked MO inputs without a receipt are retained.
clean:
	python3 ../tools/safe_clean.py --scope lang --goal clean

clean-plan:
	python3 ../tools/safe_clean.py --scope lang --goal clean --dry-run

.PHONY: clean clean-plan

ifneq ($(MAKECMDGOALS),)
  ifeq ($(filter-out clean clean-plan,$(MAKECMDGOALS)),)
    CLEAN_ONLY = 1
  endif
endif
ifneq ($(CLEAN_ONLY),1)
all: $(MO) $(CPH_MO)

$(MO_DIR)/cph/%/LC_MESSAGES/cataclysm-dda.mo: ./cph/%.po
	mkdir -p "$(@D)"
	msgfmt -c -o "$@" "$<"

$(MO_DIR)/%/LC_MESSAGES/cataclysm-dda.mo: $(PO_DIR)/%.po
	mkdir -p "$(@D)"
	msgfmt -f -o "$@" "$<"
	# Receipt metadata is optional; unsafe/out-of-checkout outputs are retained.
	python3 ../tools/safe_clean.py --scope lang --record-source "$<" --record-output "$@"

list_po:
	@echo $(PO)

list_mo:
	@echo $(MO)

install: $(MO) $(CPH_MO)
ifdef LOCALE_DIR
	mkdir -p $(LOCALE_DIR)
	cp -R --no-preserve=ownership $(MO_DIR)/* $(LOCALE_DIR)
endif

.PHONY: all list_po list_mo install

endif # build rules
