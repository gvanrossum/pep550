mypy:
	mypy --strict --disallow-any=generics --disallow-any=unannotated --disallow-any=decorated --disallow-any=generics contextvars.py
