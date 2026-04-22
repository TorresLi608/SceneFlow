package handlers

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"sceneflow/backend/internal/middleware"
	"sceneflow/backend/internal/models"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type generateProjectRequest struct {
	Model string `json:"model"`
}

type sceneEvent struct {
	SceneID string
	Data    gin.H
}

const maxSceneConcurrency = 3

func (h *ProjectHandler) GenerateProject(c *gin.Context) {
	userID, ok := middleware.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing user context"})
		return
	}

	projectID := strings.TrimSpace(c.Param("id"))
	if projectID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid project id"})
		return
	}

	var req generateProjectRequest
	_ = c.ShouldBindJSON(&req)

	config, warning, err := h.preflightShotPromptModel(c.Request.Context(), userID)
	if err != nil {
		h.respondPreflightError(c, err, "failed to run shot prompt model preflight")
		return
	}

	project, scenes, err := h.getProjectWithScenes(projectID, userID)
	if err != nil {
		if err == gorm.ErrRecordNotFound {
			c.JSON(http.StatusNotFound, gin.H{"error": "project not found"})
			return
		}
		if err == errProjectForbidden {
			c.JSON(http.StatusForbidden, gin.H{"error": "project does not belong to current user"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to load project"})
		return
	}

	if len(scenes) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no scenes available, parse script first"})
		return
	}

	if project.Status == "generating" {
		c.JSON(http.StatusConflict, gin.H{"error": "project is already generating"})
		return
	}

	if err := h.DB.Model(&models.Project{}).
		Where("id = ?", projectID).
		Update("status", "generating").Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update project status"})
		return
	}

	h.broadcast(projectID, gin.H{
		"type":      "PROJECT_UPDATE",
		"projectId": projectID,
		"data": gin.H{
			"status": "generating",
		},
	})

	go h.runGeneration(projectID, scenes, config)

	c.JSON(http.StatusAccepted, gin.H{
		"projectId":  projectID,
		"status":     "generating",
		"model":      strings.TrimSpace(req.Model),
		"provider":   config.Provider,
		"imageModel": config.Model,
		"warning":    warning,
		"sceneCount": len(scenes),
	})
}

func (h *ProjectHandler) getProjectWithScenes(projectID string, userID uint) (models.Project, []models.Scene, error) {
	var project models.Project
	if err := h.DB.Where("id = ?", projectID).First(&project).Error; err != nil {
		return models.Project{}, nil, err
	}

	if project.UserID != userID {
		return models.Project{}, nil, errProjectForbidden
	}

	var scenes []models.Scene
	if err := h.DB.Where("project_id = ?", projectID).Order("order_num ASC").Find(&scenes).Error; err != nil {
		return models.Project{}, nil, err
	}

	return project, scenes, nil
}

func (h *ProjectHandler) runGeneration(projectID string, scenes []models.Scene, config resolvedModelConfig) {
	updates := make(chan sceneEvent, 256)
	semaphore := make(chan struct{}, maxSceneConcurrency)

	var wg sync.WaitGroup

	for _, scene := range scenes {
		scene := scene
		wg.Add(1)
		go func() {
			defer wg.Done()

			semaphore <- struct{}{}
			defer func() {
				<-semaphore
			}()

			h.generateScene(scene, config, updates)
		}()
	}

	go func() {
		wg.Wait()
		close(updates)
	}()

	for update := range updates {
		h.broadcast(projectID, gin.H{
			"type":      "SCENE_UPDATE",
			"projectId": projectID,
			"sceneId":   update.SceneID,
			"data":      update.Data,
		})
	}

	_ = h.DB.Model(&models.Project{}).
		Where("id = ?", projectID).
		Update("status", "done").Error

	h.broadcast(projectID, gin.H{
		"type":      "PROJECT_UPDATE",
		"projectId": projectID,
		"data": gin.H{
			"status": "done",
		},
	})
}

func (h *ProjectHandler) generateScene(
	scene models.Scene,
	config resolvedModelConfig,
	updates chan<- sceneEvent,
) {
	updates <- sceneEvent{
		SceneID: scene.ID,
		Data: gin.H{
			"imageStatus":   "generating",
			"imageProgress": 5,
			"audioStatus":   "generating",
			"audioProgress": 0,
			"errorMsg":      "",
		},
	}

	_ = h.DB.Model(&models.Scene{}).
		Where("id = ?", scene.ID).
		Update("image_status", "generating").Error

	prompt := buildSceneImagePrompt(scene)
	updates <- sceneEvent{
		SceneID: scene.ID,
		Data: gin.H{
			"imageStatus":   "generating",
			"imageProgress": 20,
			"errorMsg":      "",
		},
	}

	imageCtx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()

	imageResult, err := h.Parser.GenerateImage(imageCtx, config.Provider, config.APIKey, config.Model, prompt)
	if err != nil {
		message := "AI 图片生成失败：" + trimPreflightReason(err) + "。请检查图片生成默认模型、API Key 或稍后重试。"
		_ = h.DB.Model(&models.Scene{}).
			Where("id = ?", scene.ID).
			Update("image_status", "error").Error

		updates <- sceneEvent{
			SceneID: scene.ID,
			Data: gin.H{
				"imageStatus":   "error",
				"imageProgress": 0,
				"errorMsg":      message,
			},
		}
	} else {
		updates <- sceneEvent{
			SceneID: scene.ID,
			Data: gin.H{
				"imageStatus":   "generating",
				"imageProgress": 85,
				"errorMsg":      "",
			},
		}

		imageURL, saveErr := h.persistSceneImage(scene, imageResult.Bytes, imageResult.Format)
		if saveErr != nil {
			message := "AI 图片保存失败：" + trimPreflightReason(saveErr) + "。请检查服务端生成目录配置。"
			_ = h.DB.Model(&models.Scene{}).
				Where("id = ?", scene.ID).
				Update("image_status", "error").Error

			updates <- sceneEvent{
				SceneID: scene.ID,
				Data: gin.H{
					"imageStatus":   "error",
					"imageProgress": 0,
					"errorMsg":      message,
				},
			}
		} else {
			_ = h.DB.Model(&models.Scene{}).
				Where("id = ?", scene.ID).
				Updates(map[string]any{
					"image_status": "success",
					"image_url":    imageURL,
				}).Error

			updates <- sceneEvent{
				SceneID: scene.ID,
				Data: gin.H{
					"imageStatus":   "success",
					"imageProgress": 100,
					"imageUrl":      imageURL,
					"errorMsg":      "",
				},
			}
		}
	}

	audioProgressSteps := []int{25, 50, 75, 100}
	for index, progress := range audioProgressSteps {
		time.Sleep(stepDelay(scene.OrderNum+1, index))
		updates <- sceneEvent{
			SceneID: scene.ID,
			Data: gin.H{
				"audioStatus":   "generating",
				"audioProgress": progress,
				"errorMsg":      "",
			},
		}
	}

	audioURL := fmt.Sprintf("https://example.com/audio/%s.mp3", scene.ID)
	audioDuration := 2.0 + float64((scene.OrderNum%5)+1)*0.8

	_ = h.DB.Model(&models.Scene{}).
		Where("id = ?", scene.ID).
		Updates(map[string]any{
			"audio_status": "success",
			"audio_url":    audioURL,
		}).Error

	updates <- sceneEvent{
		SceneID: scene.ID,
		Data: gin.H{
			"audioStatus":   "success",
			"audioProgress": 100,
			"audioUrl":      audioURL,
			"audioDuration": audioDuration,
			"errorMsg":      "",
		},
	}
}

func (h *ProjectHandler) persistSceneImage(scene models.Scene, imageBytes []byte, format string) (string, error) {
	if len(imageBytes) == 0 {
		return "", fmt.Errorf("empty image bytes")
	}

	normalizedFormat := strings.ToLower(strings.TrimSpace(format))
	if normalizedFormat == "" {
		normalizedFormat = "png"
	}

	sceneDir := filepath.Join(h.GeneratedDir, "projects", scene.ProjectID)
	if err := os.MkdirAll(sceneDir, 0o755); err != nil {
		return "", err
	}

	filename := fmt.Sprintf("%s.%s", scene.ID, normalizedFormat)
	fullPath := filepath.Join(sceneDir, filename)
	if err := os.WriteFile(fullPath, imageBytes, 0o644); err != nil {
		return "", err
	}

	baseURL := strings.TrimRight(strings.TrimSpace(h.PublicBaseURL), "/")
	if baseURL == "" {
		baseURL = "http://127.0.0.1:8080"
	}

	return fmt.Sprintf("%s/generated/projects/%s/%s", baseURL, scene.ProjectID, filename), nil
}

func buildSceneImagePrompt(scene models.Scene) string {
	visualPrompt := strings.TrimSpace(scene.VisualPrompt)
	narration := strings.TrimSpace(scene.Narration)

	if visualPrompt == "" {
		visualPrompt = narration
	}

	return fmt.Sprintf(
		"Create a cinematic anime storyboard frame for a short video. Keep one clear subject, strong composition, dramatic lighting, high detail, no text, no watermark. Scene narration: %s. Visual direction: %s.",
		narration,
		visualPrompt,
	)
}

func stepDelay(orderNum, step int) time.Duration {
	base := 110 + ((orderNum+step)%5)*40
	return time.Duration(base) * time.Millisecond
}
