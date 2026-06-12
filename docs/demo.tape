# VHS script that records docs/demo.gif — https://github.com/charmbracelet/vhs
# Prereq: gateway running in mock mode on :8001
#   GATEWAY_MOCK_MODE=true uvicorn llm_gateway.main:app --port 8001
# Record: vhs docs/demo.tape

Output docs/demo.gif

Set FontSize 14
Set Width 1150
Set Height 640
Set Padding 16
Set TypingSpeed 25ms
Set Theme "Catppuccin Mocha"

Type "# 1. One API in front of every provider (auth, routing, failover)"
Enter
Sleep 800ms
Type `curl -s localhost:8001/v1/chat -H 'X-API-Key: demo-key' -H 'Content-Type: application/json' -d '{"model": "default", "messages": [{"role": "user", "content": "Summarize our refund policy"}]}' | jq '{provider, model, cached, cost_usd, text}'`
Enter
Sleep 4s

Type "# 2. Repeat the request -> served from the semantic cache"
Enter
Sleep 800ms
Type `curl -s localhost:8001/v1/chat -H 'X-API-Key: demo-key' -H 'Content-Type: application/json' -d '{"model": "default", "messages": [{"role": "user", "content": "Summarize our refund policy"}]}' | jq '{cached, provider, model}'`
Enter
Sleep 3500ms

Type "# 3. Everything is observable: cache hits, per-client spend, breaker states"
Enter
Sleep 800ms
Type `curl -s localhost:8001/metrics -H 'X-API-Key: demo-key' | jq`
Enter
Sleep 5s
