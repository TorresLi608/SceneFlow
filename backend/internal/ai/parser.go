package ai

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type SceneDraft struct {
	Narration    string `json:"narration"`
	VisualPrompt string `json:"visualPrompt"`
}

type ParseResult struct {
	Scenes  []SceneDraft
	Source  string
	Warning string
}

type Parser struct {
	httpClient *http.Client
}

func NewParser() *Parser {
	return &Parser{
		httpClient: &http.Client{Timeout: 45 * time.Second},
	}
}

func (p *Parser) ParseScript(
	ctx context.Context,
	provider string,
	apiKey string,
	model string,
	script string,
) (ParseResult, error) {
	normalizedScript := strings.TrimSpace(script)
	if normalizedScript == "" {
		return ParseResult{}, errors.New("script is empty")
	}

	normalizedProvider := strings.ToLower(strings.TrimSpace(provider))
	selectedModel := pickModel(normalizedProvider, model)

	if normalizedProvider == "" || strings.TrimSpace(apiKey) == "" {
		return ParseResult{}, errors.New("missing active script model config")
	}

	scenes, err := p.parseWithProvider(ctx, normalizedProvider, strings.TrimSpace(apiKey), selectedModel, normalizedScript)
	if err != nil {
		return ParseResult{}, err
	}

	return ParseResult{
		Scenes: scenes,
		Source: "llm",
	}, nil
}

func (p *Parser) ValidateProviderModel(
	ctx context.Context,
	provider string,
	apiKey string,
	model string,
) error {
	normalizedProvider := strings.ToLower(strings.TrimSpace(provider))
	plainKey := strings.TrimSpace(apiKey)
	if normalizedProvider == "" {
		return errors.New("provider is required")
	}
	if plainKey == "" {
		return errors.New("apiKey is required")
	}

	endpoint, err := endpointForProvider(normalizedProvider)
	if err != nil {
		return err
	}

	payload := map[string]any{
		"model":       pickModel(normalizedProvider, model),
		"temperature": 0,
		"max_tokens":  12,
		"messages": []map[string]string{
			{
				"role":    "user",
				"content": "reply with ok",
			},
		},
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+plainKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := p.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	if resp.StatusCode >= 300 {
		message := strings.TrimSpace(string(respBody))
		if len(message) > 180 {
			message = message[:180] + "..."
		}
		return fmt.Errorf("provider status %d: %s", resp.StatusCode, message)
	}

	var completion struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(respBody, &completion); err != nil {
		return err
	}

	if len(completion.Choices) == 0 {
		return errors.New("empty choices from provider")
	}

	content := strings.TrimSpace(completion.Choices[0].Message.Content)
	if content == "" {
		return errors.New("empty content from provider")
	}

	return nil
}

func (p *Parser) parseWithProvider(
	ctx context.Context,
	provider string,
	apiKey string,
	model string,
	script string,
) ([]SceneDraft, error) {
	endpoint, err := endpointForProvider(provider)
	if err != nil {
		return nil, err
	}

	content, err := p.callChatCompletions(ctx, endpoint, apiKey, model, script)
	if err != nil {
		return nil, err
	}

	scenes, err := decodeScenes(content)
	if err != nil {
		return nil, err
	}

	if len(scenes) == 0 {
		return nil, errors.New("no scenes in parsed output")
	}

	if len(scenes) > 20 {
		scenes = scenes[:20]
	}

	return scenes, nil
}

func (p *Parser) callChatCompletions(
	ctx context.Context,
	endpoint string,
	apiKey string,
	model string,
	script string,
) (string, error) {
	payload := map[string]any{
		"model":       model,
		"temperature": 0.2,
		"response_format": map[string]any{
			"type": "json_object",
		},
		"messages": []map[string]string{
			{
				"role":    "system",
				"content": "You convert screenplay text into storyboard scenes. Return strict JSON only with schema: {\"scenes\":[{\"narration\":\"...\",\"visualPrompt\":\"...\"}]}",
			},
			{
				"role":    "user",
				"content": "Parse the script into 4-12 scenes. Keep narration concise and generate a cinematic anime visual prompt for each scene. Script:\n" + script,
			},
		},
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := p.httpClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	if resp.StatusCode >= 300 {
		return "", fmt.Errorf("provider status %d: %s", resp.StatusCode, strings.TrimSpace(string(respBody)))
	}

	var completion struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(respBody, &completion); err != nil {
		return "", err
	}

	if len(completion.Choices) == 0 {
		return "", errors.New("empty choices from provider")
	}

	content := strings.TrimSpace(completion.Choices[0].Message.Content)
	if content == "" {
		return "", errors.New("empty content from provider")
	}

	return content, nil
}

func decodeScenes(content string) ([]SceneDraft, error) {
	var payload struct {
		Scenes []SceneDraft `json:"scenes"`
	}

	if err := json.Unmarshal([]byte(content), &payload); err != nil {
		jsonCandidate := extractJSONObject(content)
		if jsonCandidate == "" {
			return nil, err
		}
		if decodeErr := json.Unmarshal([]byte(jsonCandidate), &payload); decodeErr != nil {
			return nil, decodeErr
		}
	}

	cleaned := make([]SceneDraft, 0, len(payload.Scenes))
	for _, scene := range payload.Scenes {
		narration := strings.TrimSpace(scene.Narration)
		visualPrompt := strings.TrimSpace(scene.VisualPrompt)
		if narration == "" {
			continue
		}
		if visualPrompt == "" {
			visualPrompt = fmt.Sprintf("anime storyboard frame, cinematic composition, %s", trimForPrompt(narration))
		}
		cleaned = append(cleaned, SceneDraft{Narration: narration, VisualPrompt: visualPrompt})
	}

	return cleaned, nil
}

func extractJSONObject(input string) string {
	start := strings.Index(input, "{")
	end := strings.LastIndex(input, "}")
	if start < 0 || end <= start {
		return ""
	}
	return input[start : end+1]
}

func fallbackScenes(script string) []SceneDraft {
	lines := strings.Split(script, "\n")
	cleaned := make([]string, 0, len(lines))
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "" {
			continue
		}
		cleaned = append(cleaned, trimmed)
		if len(cleaned) >= 12 {
			break
		}
	}

	if len(cleaned) == 0 {
		cleaned = []string{
			"主角在夜色中缓缓回头，远处霓虹映在雨后的街道上。",
			"镜头拉近到主角眼神，旁白进入情绪高潮。",
		}
	}

	scenes := make([]SceneDraft, 0, len(cleaned))
	for index, line := range cleaned {
		scenes = append(scenes, SceneDraft{
			Narration: line,
			VisualPrompt: fmt.Sprintf(
				"anime storyboard frame %d, %s, dramatic lighting, cinematic composition",
				index+1,
				trimForPrompt(line),
			),
		})
	}

	return scenes
}

func pickModel(provider string, requested string) string {
	trimmed := strings.TrimSpace(requested)
	if trimmed != "" {
		switch provider {
		case "qwen", "deepseek", "doubao", "openai":
			return strings.ToLower(trimmed)
		default:
			return trimmed
		}
	}

	switch provider {
	case "deepseek":
		return "deepseek-chat"
	case "qwen":
		return "qwen-plus"
	case "doubao":
		return "doubao-seed-1-6-250615"
	default:
		return "gpt-4o-mini"
	}
}

func endpointForProvider(provider string) (string, error) {
	switch provider {
	case "openai":
		return "https://api.openai.com/v1/chat/completions", nil
	case "deepseek":
		return "https://api.deepseek.com/chat/completions", nil
	case "qwen":
		return "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", nil
	case "doubao":
		return "https://ark.cn-beijing.volces.com/api/v3/chat/completions", nil
	default:
		return "", fmt.Errorf("unsupported provider: %s", provider)
	}
}

func trimForPrompt(input string) string {
	trimmed := strings.TrimSpace(input)
	if len(trimmed) <= 100 {
		return trimmed
	}
	return trimmed[:100]
}
