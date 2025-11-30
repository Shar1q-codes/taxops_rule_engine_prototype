import json
from engine import RuleEngine

doc=json.load(open('sample_data/f1098_issues.json'))
eng=RuleEngine()
env=eng._build_environment(doc, doc['doc_type'], doc['tax_year'], eng.registry.get_year_params(doc['tax_year']), supported_years=eng.registry.supported_years)
print('recipient_tin:', env.get('recipient_tin'))
print('missing:', env['missing'](env.get('recipient_tin')))
expr="missing(recipient_tin)"
print('expr eval', eval(expr, {'__builtins__':{}}, env))
