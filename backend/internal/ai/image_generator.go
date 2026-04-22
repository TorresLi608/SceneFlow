package ai

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

type ImageResult struct {
	Bytes  []byte
	Format string
}

func (p *Parser) ValidateImageModel(
	ctx context.Context,
	provider string,
	apiKey string,
	model string,
) error {
	normalizedProvider := strings.ToLower(strings.TrimSpace(provider))
	plainKey := strings.TrimSpace(apiKey)
	selectedModel := strings.TrimSpace(model)

	if normalizedProvider == "" {
		return fmt.Errorf("provider is required")
	}
	if plainKey == "" {
		return fmt.Errorf("apiKey is required")
	}
	if normalizedProvider != "openai" {
		return fmt.Errorf("image generation currently only supports provider openai")
	}
	if selectedModel == "" {
		return fmt.Errorf("image purpose requires modelSeries")
	}

	_, err := p.generateOpenAIImage(
		ctx,
		plainKey,
		selectedModel,
		"Generate a simple gray square with soft light.",
		"1024x1024",
		"low",
	)
	return err
}

func (p *Parser) GenerateImage(
	ctx context.Context,
	provider string,
	apiKey string,
	model string,
	prompt string,
) (ImageResult, error) {
	normalizedProvider := strings.ToLower(strings.TrimSpace(provider))
	plainKey := strings.TrimSpace(apiKey)
	selectedModel := strings.TrimSpace(model)
	normalizedPrompt := strings.TrimSpace(prompt)

	if normalizedProvider == "" {
		return ImageResult{}, fmt.Errorf("provider is required")
	}
	if plainKey == "" {
		return ImageResult{}, fmt.Errorf("apiKey is required")
	}
	if selectedModel == "" {
		return ImageResult{}, fmt.Errorf("model is required")
	}
	if normalizedPrompt == "" {
		return ImageResult{}, fmt.Errorf("prompt is empty")
	}

	switch normalizedProvider {
	case "openai":
		return p.generateOpenAIImage(ctx, plainKey, selectedModel, normalizedPrompt, "1536x1024", "medium")
	default:
		return ImageResult{}, fmt.Errorf("image generation currently only supports provider %s", "openai")
	}
}

func (p *Parser) generateOpenAIImage(
	ctx context.Context,
	apiKey string,
	model string,
	prompt string,
	size string,
	quality string,
) (ImageResult, error) {
	payload := map[string]any{
		"model":         model,
		"prompt":        prompt,
		"size":          size,
		"quality":       quality,
		"output_format": "png",
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return ImageResult{}, err
	}

	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		"https://api.openai.com/v1/images/generations",
		bytes.NewReader(body),
	)
	if err != nil {
		return ImageResult{}, err
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)
	req.Header.Set("Content-Type", "application/json")

	resp, err := p.httpClient.Do(req)
	if err != nil {
		return ImageResult{}, err
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return ImageResult{}, err
	}

	if resp.StatusCode >= 300 {
		message := strings.TrimSpace(string(respBody))
		if len(message) > 220 {
			message = message[:220] + "..."
		}
		return ImageResult{}, fmt.Errorf("provider status %d: %s", resp.StatusCode, message)
	}

	var imageResp struct {
		Data []struct {
			B64JSON string `json:"b64_json"`
		} `json:"data"`
		OutputFormat string `json:"output_format"`
	}
	if err := json.Unmarshal(respBody, &imageResp); err != nil {
		return ImageResult{}, err
	}

	if len(imageResp.Data) == 0 || strings.TrimSpace(imageResp.Data[0].B64JSON) == "" {
		return ImageResult{}, fmt.Errorf("empty image response")
	}

	imageBytes, err := base64.StdEncoding.DecodeString(imageResp.Data[0].B64JSON)
	if err != nil {
		return ImageResult{}, err
	}

	format := strings.TrimSpace(imageResp.OutputFormat)
	if format == "" {
		format = "png"
	}

	return ImageResult{
		Bytes:  imageBytes,
		Format: format,
	}, nil
}
