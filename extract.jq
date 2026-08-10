if .type == "summary" then "SUMMARY: " + (.summary // "")
elif .message.content == null then empty
elif (.message.content | type) == "string" then "--- " + .message.role + " ---\n" + .message.content
else
  (.message.content[] |
    if .type == "text" then "--- " + .role + " text ---\n" + .text
    elif .type == "tool_use" then "--- tool_use: " + .name + " ---\n" + (.input | tostring)
    elif .type == "tool_result" then
      (if (.content|type)=="array" then ([.content[] | select(.type=="text") | .text] | join("\n")) elif (.content|type)=="string" then .content else "" end) as $t
      | "--- tool_result ---\n" + ($t // "")
    else empty end
  )
end
