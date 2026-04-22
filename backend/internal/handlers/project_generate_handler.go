package handlers

import (
	"fmt"
	"net/http"
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

	go h.runGeneration(projectID, scenes)

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

func (h *ProjectHandler) runGeneration(projectID string, scenes []models.Scene) {
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

			h.generateScene(scene, updates)
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

func (h *ProjectHandler) generateScene(scene models.Scene, updates chan<- sceneEvent) {
	updates <- sceneEvent{
		SceneID: scene.ID,
		Data: gin.H{
			"imageStatus":   "generating",
			"imageProgress": 0,
			"audioStatus":   "generating",
			"audioProgress": 0,
			"errorMsg":      "",
		},
	}

	imageProgressSteps := []int{15, 35, 55, 80, 100}
	for index, progress := range imageProgressSteps {
		time.Sleep(stepDelay(scene.OrderNum, index))
		updates <- sceneEvent{
			SceneID: scene.ID,
			Data: gin.H{
				"imageStatus":   "generating",
				"imageProgress": progress,
				"errorMsg":      "",
			},
		}
	}

	imageURL := fmt.Sprintf("https://picsum.photos/seed/%s/960/540", scene.ID)
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

func stepDelay(orderNum, step int) time.Duration {
	base := 110 + ((orderNum+step)%5)*40
	return time.Duration(base) * time.Millisecond
}
