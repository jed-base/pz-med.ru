# Demo duty consistency

After all demo seed/enrichment steps, `validate_duty_demo.py` removes duty assignments that overlap a confirmed absence or an approved vacation. This is necessary because demo seed scripts insert records directly and therefore bypass the normal application service validation used by manager assignment and self-signup.
