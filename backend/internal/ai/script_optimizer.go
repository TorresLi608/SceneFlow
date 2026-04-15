package ai

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

type OptimizeResult struct {
	OptimizedScript string   `json:"optimizedScript"`
	Tips            []string `json:"tips"`
	Source          string   `json:"source"`
	Warning         string   `json:"warning,omitempty"`
}

func (p *Parser) OptimizeScript(
	ctx context.Context,
	provider string,
	apiKey string,
	model string,
	script string,
) (OptimizeResult, error) {
	normalizedScript := strings.TrimSpace(script)
	if normalizedScript == "" {
		return OptimizeResult{}, fmt.Errorf("script is empty")
	}

	normalizedProvider := strings.ToLower(strings.TrimSpace(provider))
	selectedModel := pickModel(normalizedProvider, model)

	if normalizedProvider == "" || strings.TrimSpace(apiKey) == "" {
		return fallbackOptimize(normalizedScript, "missing active script config, fallback optimizer used"), nil
	}

	endpoint, err := endpointForProvider(normalizedProvider)
	if err != nil {
		return fallbackOptimize(normalizedScript, "unsupported provider, fallback optimizer used"), nil
	}

	payload := map[string]any{
		"model":       selectedModel,
		"temperature": 0.3,
		"response_format": map[string]any{
			"type": "json_object",
		},
		"messages": []map[string]string{
			{
				"role":    "system",
				"content": "You are a screenplay doctor. Return strict JSON with fields optimizedScript (string) and tips (string array).",
			},
			{
				"role":    "user",
				"content": "Polish and optimize this script for short anime video production. Keep style concise and cinematic. Script:\n" + normalizedScript,
			},
		},
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return OptimizeResult{}, err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return OptimizeResult{}, err
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := p.httpClient.Do(req)
	if err != nil {
		return fallbackOptimize(normalizedScript, "provider optimize call failed, fallback optimizer used"), nil
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return OptimizeResult{}, err
	}

	if resp.StatusCode >= 300 {
		return fallbackOptimize(normalizedScript, "provider optimize failed, fallback optimizer used"), nil
	}

	var completion struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(respBody, &completion); err != nil {
		return OptimizeResult{}, err
	}

	if len(completion.Choices) == 0 {
		return fallbackOptimize(normalizedScript, "empty optimize response, fallback optimizer used"), nil
	}

	content := strings.TrimSpace(completion.Choices[0].Message.Content)
	if content == "" {
		return fallbackOptimize(normalizedScript, "empty optimize content, fallback optimizer used"), nil
	}

	result, err := decodeOptimizeResult(content)
	if err != nil {
		fallback := fallbackOptimize(normalizedScript, "invalid optimize json, fallback optimizer used")
		return fallback, nil
	}

	result.Source = "llm"
	return result, nil
}

func decodeOptimizeResult(content string) (OptimizeResult, error) {
	candidate := content
	if !strings.HasPrefix(strings.TrimSpace(content), "{") {
		candidate = extractJSONObject(content)
	}

	var payload struct {
		OptimizedScript string   `json:"optimizedScript"`
		Tips            []string `json:"tips"`
	}
	if err := json.Unmarshal([]byte(candidate), &payload); err != nil {
		return OptimizeResult{}, err
	}

	optimized := strings.TrimSpace(payload.OptimizedScript)
	if optimized == "" {
		return OptimizeResult{}, fmt.Errorf("optimizedScript is empty")
	}

	tips := make([]string, 0, len(payload.Tips))
	for _, tip := range payload.Tips {
		trimmed := strings.TrimSpace(tip)
		if trimmed != "" {
			tips = append(tips, trimmed)
		}
	}
	if len(tips) == 0 {
		tips = []string{"补充镜头情绪变化", "每段保持单一动作焦点", "减少重复描述，增加视觉细节"}
	}

	return OptimizeResult{OptimizedScript: optimized, Tips: tips}, nil
}

func fallbackOptimize(script string, warning string) OptimizeResult {
	lines := strings.Split(script, "\n")
	cleaned := make([]string, 0, len(lines))
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		cleaned = append(cleaned, trimmed)
	}

	if len(cleaned) == 0 {
		cleaned = []string{"镜头推入主角", "环境音逐渐增强", "情绪转折在第三幕发生"}
	}

	optimized := make([]string, 0, len(cleaned))
	for _, line := range cleaned {
		optimized = append(optimized, line+"（强化镜头节奏与情绪张力）")
	}

	return OptimizeResult{
		OptimizedScript: strings.Join(optimized, "\n"),
		Tips: []string{
			"把每一行写成单镜头动作，降低歧义",
			"给关键镜头增加情绪词和光线词",
			"前3镜头快速建立冲突，结尾保留悬念",
		},
		Source:  "fallback",
		Warning: warning,
	}
}
