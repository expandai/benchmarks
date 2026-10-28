# expandai/benchmarks: each benchmark lives in its own directory with its own Makefile.
# Any target given here is forwarded to search/ (the only benchmark so far): `make test` == `make -C search test`.

BENCHMARKS := search

.PHONY: help $(BENCHMARKS)

help: ## List the benchmarks and their targets
	@for b in $(BENCHMARKS); do echo "$$b/:"; $(MAKE) -s -C $$b help | sed 's/^/  /'; done

%:
	@$(MAKE) -C search $@
