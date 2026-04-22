package handlers

import (
	"net/http"
	"strings"
	"time"

	"sceneflow/backend/internal/middleware"
	"sceneflow/backend/internal/models"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type optimizeScriptRequest struct {
	Script string `json:"script"`
	Model  string `json:"model"`
}

type generateVideoRequest struct {
	Model string `json:"model"`
}

func (h *ProjectHandler) DeleteProject(c *gin.Context) {
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

	project, err := h.loadProjectForUser(projectID, userID)
	if err != nil {
		if err == gorm.ErrRecordNotFound {
			c.Status(http.StatusNoContent)
			return
		}
		if err == errProjectForbidden {
			c.JSON(http.StatusForbidden, gin.H{"error": "project does not belong to current user"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to load project"})
		return
	}

	if err := h.DB.Delete(&project).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to delete project"})
		return
	}

	h.broadcast(projectID, gin.H{
		"type":      "PROJECT_DELETED",
		"projectId": projectID,
	})

	c.Status(http.StatusNoContent)
}

func (h *ProjectHandler) OptimizeScript(c *gin.Context) {
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

	project, err := h.loadProjectForUser(projectID, userID)
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

	var req optimizeScriptRequest
	_ = c.ShouldBindJSON(&req)

	script := strings.TrimSpace(req.Script)
	if script == "" {
		script = strings.TrimSpace(project.OriginalScript)
	}
	if script == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "script is required"})
		return
	}

	config, err := h.preflightModelConfig(c.Request.Context(), userID, "script", "故事生成/剧本优化")
	if err != nil {
		h.respondPreflightError(c, err, "failed to run script model preflight")
		return
	}

	selectedModel := strings.TrimSpace(req.Model)
	if selectedModel == "" {
		selectedModel = config.Model
	}

	result, err := h.Parser.OptimizeScript(c.Request.Context(), config.Provider, config.APIKey, selectedModel, script)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "failed to optimize script: " + err.Error()})
		return
	}

	if err := h.DB.Model(&models.Project{}).
		Where("id = ?", projectID).
		Updates(map[string]any{"original_script": result.OptimizedScript, "status": "idle"}).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to save optimized script"})
		return
	}

	h.broadcast(projectID, gin.H{
		"type":      "PROJECT_UPDATE",
		"projectId": projectID,
		"data": gin.H{
			"status":          "idle",
			"optimizedScript": result.OptimizedScript,
			"warning":         result.Warning,
		},
	})

	c.JSON(http.StatusOK, gin.H{
		"projectId":        projectID,
		"optimizedScript":  result.OptimizedScript,
		"tips":             result.Tips,
		"source":           result.Source,
		"warning":          result.Warning,
		"appliedToProject": true,
	})
}

func (h *ProjectHandler) GenerateVideo(c *gin.Context) {
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

	if project.Status == "video_generating" {
		c.JSON(http.StatusConflict, gin.H{"error": "project video is already generating"})
		return
	}

	config, err := h.preflightModelConfig(c.Request.Context(), userID, "video", "视频生成")
	if err != nil {
		h.respondPreflightError(c, err, "failed to run video model preflight")
		return
	}

	var req generateVideoRequest
	_ = c.ShouldBindJSON(&req)
	selectedModel := strings.TrimSpace(req.Model)
	if selectedModel == "" {
		selectedModel = config.Model
	}

	if err := h.DB.Model(&models.Project{}).
		Where("id = ?", projectID).
		Updates(map[string]any{"status": "video_generating", "video_status": "generating"}).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update project status"})
		return
	}

	h.broadcast(projectID, gin.H{
		"type":      "PROJECT_UPDATE",
		"projectId": projectID,
		"data": gin.H{
			"status":      "video_generating",
			"videoStatus": "generating",
			"videoModel":  selectedModel,
		},
	})

	go h.runVideoGeneration(projectID, selectedModel)

	c.JSON(http.StatusAccepted, gin.H{
		"projectId": projectID,
		"status":    "video_generating",
		"model":     selectedModel,
	})
}

func (h *ProjectHandler) runVideoGeneration(projectID string, model string) {
	steps := []int{10, 25, 40, 60, 75, 90, 100}
	for _, progress := range steps {
		time.Sleep(350 * time.Millisecond)
		h.broadcast(projectID, gin.H{
			"type":      "VIDEO_UPDATE",
			"projectId": projectID,
			"data": gin.H{
				"videoStatus":   "generating",
				"videoProgress": progress,
				"videoModel":    model,
			},
		})
	}

	videoURL := "https://example.com/video/" + projectID + ".mp4"
	_ = h.DB.Model(&models.Project{}).
		Where("id = ?", projectID).
		Updates(map[string]any{
			"status":       "done",
			"video_status": "success",
			"video_url":    videoURL,
		}).Error

	h.broadcast(projectID, gin.H{
		"type":      "PROJECT_UPDATE",
		"projectId": projectID,
		"data": gin.H{
			"status":      "done",
			"videoStatus": "success",
			"videoUrl":    videoURL,
			"videoModel":  model,
		},
	})
}
