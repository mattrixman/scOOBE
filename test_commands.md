I lean on my command history pretty heavily,  here's a list of commands I frequently recall for testing scOOBE

get_partner_control TA9EQC3BCEMTT $PROPFILE | jq '.name = "FOOBAR" | del(.id)' | set_partner_control $PROPFILE
get_partner_control 86R64VAF1SMQM dev1 | jq 'del(.criteria.country) | del(.id) | del(.db_id) | .name="PlanTrialPC_A" | .criteria.reseller= { "uuid":"0JG5YNPFE4PRA", "sysPrin":""}' | new_partner_control deve
get_reseller 9 $PROPFILE | jq '.name = "FOORESELLER"' | set_reseller $PROPFILE


