I lean on my command history pretty heavily,  here's a list of commands I frequently recall for testing scOOBE

get_partner_control TA9EQC3BCEMTT $PROPFILE | jq '.name = "FOOBAR" | del(.id)' | set_partner_control $PROPFILE

get_partner_control 86R64VAF1SMQM dev1 | jq 'del(.criteria.country) | del(.id) | del(.db_id) | .name="PlanTrialPC_A" | .criteria.reseller= { "uuid":"0JG5YNPFE4PRA", "sysPrin":""}' | new_partner_control deve

get_reseller 9 $PROPFILE | jq '.name = "FOORESELLER"' | set_reseller $PROPFILE

get_plan 3 $PROPFILE | jq 'del(.db_id) | del(.id)' | new_plan $PROPFILE

echo '{"marker" : 306 }' | new_merchant US 0AAV0JTGYVMYP dev1

curl "http://$TARGET/v3/eventing/subscriptions?orderBy=name%20ASC&limit=100" --cookie "$COOKIE" \
                      | jq '.elements[]
                            |  select(.parameters
                                      | fromjson
                                      | select(.url != null)
                                      | .url
                                      | contains("/billing/v1/merchants/{mId}/accountStatus"))'

event_subscription BYZG7R7HMMTYY dev1 | jq '.name = "DELETE ME" | del(.id)' | new_event_subscription dev1

permissions dev1

my_permissions dev1

set_permission 38 dev1
