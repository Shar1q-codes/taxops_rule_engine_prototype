import json
from engine import RuleEngine

doc=json.load(open('sample_data/misc_issues.json'))
eng=RuleEngine()
env=eng._build_environment(doc, doc['doc_type'], doc['tax_year'], eng.registry.get_year_params(doc['tax_year']), supported_years=eng.registry.supported_years)
safe_globals={'__builtins__': {}}
safe_globals.update(env)
expr = "any((not si.get('state_code') or len(str(si.get('state_code')).strip()) != 2 or re_match(r'[^A-Za-z]{2}', str(si.get('state_code')).strip())) for si in get('state_items', []))"
print(eval(expr, safe_globals, env))
