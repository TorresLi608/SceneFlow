package handlers

import (
	"net/http"
	"strings"
	"time"

	"sceneflow/backend/internal/auth"
	"sceneflow/backend/internal/models"
	"sceneflow/backend/internal/ws"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"gorm.io/gorm"
)

type ProjectWSHandler struct {
	DB        *gorm.DB
	JWTSecret string
	Hub       *ws.Hub
}

var wsUpgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(*http.Request) bool {
		return true
	},
}

func (h *ProjectWSHandler) ServeWS(c *gin.Context) {
	if h.Hub == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "ws hub is not available"})
		return
	}

	projectID := strings.TrimSpace(c.Param("id"))
	if projectID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid project id"})
		return
	}

	token := strings.TrimSpace(c.Query("token"))
	if token == "" {
		authHeader := strings.TrimSpace(c.GetHeader("Authorization"))
		token = strings.TrimSpace(strings.TrimPrefix(authHeader, "Bearer"))
	}
	if token == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing token"})
		return
	}

	claims, err := auth.ParseToken(token, h.JWTSecret)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
		return
	}

	allowed, err := h.projectAccessible(projectID, claims.UserID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to verify project ownership"})
		return
	}
	if !allowed {
		c.JSON(http.StatusForbidden, gin.H{"error": "project does not belong to current user"})
		return
	}

	conn, err := wsUpgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		return
	}

	client := ws.NewClient(h.Hub, conn, projectID)
	h.Hub.Register(client)

	go client.WritePump()
	go client.ReadPump()

	_ = h.Hub.PublishJSON(projectID, gin.H{
		"type":      "WS_CONNECTED",
		"projectId": projectID,
		"data": gin.H{
			"connectedAt": time.Now().UTC().Format(time.RFC3339),
		},
	})
}

func (h *ProjectWSHandler) projectAccessible(projectID string, userID uint) (bool, error) {
	var project models.Project
	err := h.DB.Select("id", "user_id").Where("id = ?", projectID).First(&project).Error
	if err == nil {
		return project.UserID == userID, nil
	}
	if err == gorm.ErrRecordNotFound {
		return true, nil
	}
	return false, err
}
