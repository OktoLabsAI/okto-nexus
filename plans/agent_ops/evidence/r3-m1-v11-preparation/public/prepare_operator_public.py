from pathlib import Path
R=Path(__file__).resolve().parent
s=(R/'curate_public_v11.py').read_text()
s=s.replace("OUT=R/'public'", "OUT=R/'public-operator-final'")
s=s.replace('reviewed-final-entry-gates','operator-final-entry-gates')
s=s.replace('assert len(unique)==188','assert len(unique)==221')
s=s.replace("'final-composed-origins'):", "'final-composed-origins','operator-final-origins','reviewed-final-entry-gates'):")
s=s.replace('OFFLINE_V11_QUALIFIED_FOR_ROOT_REVIEW_NOT_AUTHORIZED','OFFLINE_V11_QUALIFIED_STANDING_AUTHORIZATION_TECHNICAL_BINDING_PENDING')
s=s.replace("'real_approval_created':False,", "'real_approval_created':False,'technical_v11_binding_created':False,'standing_user_authorization_received':True,'new_human_approval_of_hash_required':False,")
(R/'curate_public_operator_final.py').write_bytes(s.encode())
print('Prepared new public curation; historical public untouched')
