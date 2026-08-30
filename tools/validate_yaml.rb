require 'yaml'

path = File.join(File.dirname(__FILE__), '..', 'configs', 'dsh', 'qwen38.provider.example.yaml')
data = YAML.load_file(path)
provider = data.dig('llm-pi-ai', 'providers', 'qwen38')
raise 'qwen38 provider missing' unless provider
raise 'apiKeyEnv missing' unless provider['apiKeyEnv'] == 'QWEN38_API_KEY'
raise 'api missing' unless provider['api'] == 'openai-completions'
raise 'baseURL missing' unless provider['baseURL'] == 'http://qwen-host.example:8098/v1'
raise 'chat suffix in baseURL' if provider['baseURL'].include?('/chat/completions')
raise 'transport missing' unless provider['transport'] == 'sse'
raise 'compat missing' unless provider.dig('compat', 'supportsDeveloperRole') == false
raise 'maxTokensField missing' unless provider.dig('compat', 'maxTokensField') == 'max_tokens'
raise 'reasoning compat missing' unless provider.dig('compat', 'supportsReasoningEffort') == true
raise 'thinking format missing' unless provider.dig('compat', 'thinkingFormat') == 'openai'
raise 'default model missing' unless data.dig('agent-default-model', 'provider') == 'qwen38'
raise 'default model wrong' unless data.dig('agent-default-model', 'model') == 'Qwen3.8-27B-Q3'
raise 'default reasoning missing' unless data.dig('agent-default-model', 'reasoningEffort') == 'max'
raise 'reasoning default missing' unless %w[xhigh max].include?(provider['reasoning'])
raise 'models missing' unless provider['models'].length == 2
q3 = provider['models'][0]
q2 = provider['models'][1]
raise 'Q3 contextWindow wrong' unless q3['id'] == 'Qwen3.8-27B-Q3' && q3['contextWindow'] == 87_063 && q3['maxTokens'] == 8192
raise 'Q2 contextWindow wrong' unless q2['id'] == 'Qwen3.8-27B-Q2' && q2['contextWindow'] == 144_000 && q2['maxTokens'] == 8192
expected_efforts = %w[off minimal low medium high xhigh max]
raise 'Q3 reasoning levels wrong' unless q3['reasoningEfforts'].keys == expected_efforts
raise 'Q2 reasoning levels wrong' unless q2['reasoningEfforts'].keys == expected_efforts
expected_wire_efforts = {
  'off' => 'none',
  'minimal' => 'minimal',
  'low' => 'low',
  'medium' => 'medium',
  'high' => 'high',
  'xhigh' => 'extra',
  'max' => 'ultra'
}
raise 'Q3 reasoning wire map wrong' unless q3['reasoningEfforts'] == expected_wire_efforts
raise 'Q2 reasoning wire map wrong' unless q2['reasoningEfforts'] == expected_wire_efforts
puts 'YAML OK'
