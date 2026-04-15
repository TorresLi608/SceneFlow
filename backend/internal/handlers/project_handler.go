package handlers

import (
	"errors"
	"net/http"
	"strings"

	"sceneflow/backend/internal/ai"
	"sceneflow/backend/internal/middleware"
	"sceneflow/backend/internal/models"
	"sceneflow/backend/internal/security"
	"sceneflow/backend/internal/utils"
	"sceneflow/backend/internal/ws"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type ProjectHandler struct {
	DB     *gorm.DB
	AESKey []byte
	Parser *ai.Parser
	Hub    *ws.Hub
}

type parseProjectRequest struct {
	Script string `json:"script" binding:"required"`
	Model  string `json:"model"`
}

var errProjectForbidden = errors.New("project forbidden")

func (h *ProjectHandler) ParseProject(c *gin.Context) {
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

	var req parseProjectRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	script := strings.TrimSpace(req.Script)
	if script == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "script is required"})
		return
	}

	project, err := h.ensureProject(projectID, userID, script)
	if err != nil {
		if errors.Is(err, errProjectForbidden) {
			c.JSON(http.StatusForbidden, gin.H{"error": "project does not belong to current user"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to upsert project"})
		return
	}

	provider, key, modelFromConfig, err := h.resolveProviderConfig(userID, "script")
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to resolve script provider config"})
		return
	}

	selectedModel := strings.TrimSpace(req.Model)
	if selectedModel == "" {
		selectedModel = modelFromConfig
	}

	h.broadcast(projectID, gin.H{
		"type":      "PROJECT_UPDATE",
		"projectId": projectID,
		"data": gin.H{
			"status": "parsing",
		},
	})

	result, err := h.Parser.ParseScript(c.Request.Context(), provider, key, selectedModel, script)
	if err != nil {
		_ = h.DB.Model(&project).Updates(map[string]any{"status": "idle"}).Error
		c.JSON(http.StatusBadGateway, gin.H{"error": "failed to parse script: " + err.Error()})
		return
	}

	scenes, err := h.replaceScenes(projectID, script, result.Scenes)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to persist scenes"})
		return
	}

	for _, scene := range scenes {
		h.broadcast(projectID, gin.H{
			"type":      "SCENE_UPDATE",
			"projectId": projectID,
			"sceneId":   scene.ID,
			"data": gin.H{
				"order":        scene.OrderNum,
				"narration":    scene.Narration,
				"visualPrompt": scene.VisualPrompt,
				"parseStatus":  "ready",
			},
		})
	}

	h.broadcast(projectID, gin.H{
		"type":      "PROJECT_UPDATE",
		"projectId": projectID,
		"data": gin.H{
			"status":     "idle",
			"sceneCount": len(scenes),
			"source":     result.Source,
			"warning":    result.Warning,
		},
	})

	c.JSON(http.StatusOK, gin.H{
		"projectId": projectID,
		"status":    "idle",
		"source":    result.Source,
		"warning":   result.Warning,
		"scenes":    serializeScenes(scenes),
	})
}

func (h *ProjectHandler) ensureProject(projectID string, userID uint, script string) (models.Project, error) {
	var project models.Project
	err := h.DB.Where("id = ?", projectID).First(&project).Error
	switch {
	case err == nil:
		if project.UserID != userID {
			return models.Project{}, errProjectForbidden
		}
		project.OriginalScript = script
		project.Status = "parsing"
		if saveErr := h.DB.Save(&project).Error; saveErr != nil {
			return models.Project{}, saveErr
		}
		return project, nil
	case err == gorm.ErrRecordNotFound:
		project = models.Project{
			ID:             projectID,
			UserID:         userID,
			OriginalScript: script,
			Status:         "parsing",
			VideoStatus:    "idle",
		}
		if createErr := h.DB.Create(&project).Error; createErr != nil {
			return models.Project{}, createErr
		}
		return project, nil
	default:
		return models.Project{}, err
	}
}

func (h *ProjectHandler) replaceScenes(projectID string, script string, drafts []ai.SceneDraft) ([]models.Scene, error) {
	tx := h.DB.Begin()

	if err := tx.Model(&models.Project{}).
		Where("id = ?", projectID).
		Updates(map[string]any{"original_script": script, "status": "idle"}).Error; err != nil {
		tx.Rollback()
		return nil, err
	}

	if err := tx.Where("project_id = ?", projectID).Delete(&models.Scene{}).Error; err != nil {
		tx.Rollback()
		return nil, err
	}

	scenes := make([]models.Scene, 0, len(drafts))
	for index, draft := range drafts {
		scene := models.Scene{
			ID:           utils.NewID("scene"),
			ProjectID:    projectID,
			OrderNum:     index + 1,
			Narration:    draft.Narration,
			VisualPrompt: draft.VisualPrompt,
			ImageStatus:  "idle",
			AudioStatus:  "idle",
		}
		if err := tx.Create(&scene).Error; err != nil {
			tx.Rollback()
			return nil, err
		}
		scenes = append(scenes, scene)
	}

	if err := tx.Commit().Error; err != nil {
		return nil, err
	}

	return scenes, nil
}

func (h *ProjectHandler) loadProjectForUser(projectID string, userID uint) (models.Project, error) {
	var project models.Project
	if err := h.DB.Where("id = ?", projectID).First(&project).Error; err != nil {
		return models.Project{}, err
	}

	if project.UserID != userID {
		return models.Project{}, errProjectForbidden
	}

	return project, nil
}

func (h *ProjectHandler) resolveProviderConfig(userID uint, purpose string) (provider string, apiKey string, model string, err error) {
	purpose = normalizePurpose(purpose)
	var config models.UserConfig
	if err := h.DB.Where("user_id = ? AND purpose = ? AND is_active = ?", userID, purpose, true).
		Order("updated_at DESC").
		First(&config).Error; err != nil {
		if err == gorm.ErrRecordNotFound {
			return "", "", "", nil
		}
		return "", "", "", err
	}

	plainKey, err := security.Decrypt(config.EncryptedKey, h.AESKey)
	if err != nil {
		return "", "", "", err
	}

	return strings.ToLower(strings.TrimSpace(config.Provider)), plainKey, strings.TrimSpace(config.ModelName), nil
}

func (h *ProjectHandler) broadcast(projectID string, payload any) {
	if h.Hub == nil {
		return
	}
	_ = h.Hub.PublishJSON(projectID, payload)
}

func serializeScenes(scenes []models.Scene) []gin.H {
	output := make([]gin.H, 0, len(scenes))
	for _, scene := range scenes {
		output = append(output, gin.H{
			"id":           scene.ID,
			"order":        scene.OrderNum,
			"narration":    scene.Narration,
			"visualPrompt": scene.VisualPrompt,
			"image": gin.H{
				"url":      emptyToNil(scene.ImageURL),
				"status":   scene.ImageStatus,
				"progress": 0,
			},
			"audio": gin.H{
				"url":      emptyToNil(scene.AudioURL),
				"status":   scene.AudioStatus,
				"progress": 0,
				"duration": 0,
			},
		})
	}
	return output
}

func emptyToNil(value string) any {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return value
}
