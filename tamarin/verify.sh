#!/usr/bin/env bash

cd "$(dirname "$0")" || exit 1
status=0

# check <label> <file> <flag or -> <lemmas expected to be falsified, space separated>
check() {
  label=$1; file=$2; flag=$3; expected=$4
  if [ "$flag" = "-" ]; then
    out=$(tamarin-prover --prove "$file" 2>/dev/null)
  else
    out=$(tamarin-prover --prove -D="$flag" "$file" 2>/dev/null)
  fi
  summary=$(printf '%s\n' "$out" | sed -n '/summary of summaries/,$p' | grep -E '\((all-traces|exists-trace)\)')
  falsified=$(printf '%s\n' "$summary" | grep 'falsified' | awk '{print $1}' | sort | tr '\n' ' ' | sed 's/ $//')
  wanted=$(printf '%s\n' $expected | sort | tr '\n' ' ' | sed 's/ $//')
  other=$(printf '%s\n' "$summary" | grep -v -E 'verified|falsified')
  if [ -n "$summary" ] && [ -z "$other" ] && [ "$falsified" = "$wanted" ] \
     && printf '%s\n' "$out" | grep -q 'All wellformedness checks were successful'; then
    printf 'ok    %-26s falsified: %s\n' "$label" "${falsified:-none}"
  else
    printf 'FAIL  %-26s falsified: %s (expected: %s)\n' "$label" "${falsified:-none}" "${wanted:-none}"
    status=1
  fi
}

check "agent_written_boundary" agent_written_boundary.spthy - "executed_is_what_user_intended"
check "user_compares"          agent_written_boundary.spthy user_compares ""
check "signed_template"        signed_template.spthy - ""
check "without_c1"             signed_template.spthy without_c1             "confinement count_not_exceeded attribution"
check "without_c1_stored_once" signed_template.spthy without_c1_stored_once "count_each_unit_spent_once"
check "without_c2"             signed_template.spthy without_c2             "attribution"
check "without_c2_template_id" signed_template.spthy without_c2_template_id "attribution"
check "without_c3"             signed_template.spthy without_c3             "no_replay"
check "without_c4_scope"       signed_template.spthy without_c4_scope       "confinement attribution"
check "without_c4_amount"      signed_template.spthy without_c4_amount      "confinement"
check "without_c4_expiry"      signed_template.spthy without_c4_expiry      "confinement"
check "without_c5"             signed_template.spthy without_c5             "count_not_exceeded"
check "without_c6"             signed_template.spthy without_c6             "confinement"

exit $status
