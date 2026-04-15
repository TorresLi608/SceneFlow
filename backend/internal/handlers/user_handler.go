package handlers

import (
	"net/http"
	"strings"

	"sceneflow/backend/internal/middleware"
	"sceneflow/backend/internal/models"
	"sceneflow/backend/internal/security"

	"github.com/gin-gonic/gin"
	"gorm.io/gorm"
)

type UserHandler struct {
	DB *gorm.DB
}

type updateUserRequest struct {
	Username *string `json:"username,omitempty"`
	Password *string `json:"password,omitempty"`
}

func (h *UserHandler) GetMe(c *gin.Context) {
	user, ok := h.findCurrentUser(c)
	if !ok {
		return
	}

	c.JSON(http.StatusOK, gin.H{"user": sanitizeUser(user)})
}

func (h *UserHandler) UpdateMe(c *gin.Context) {
	user, ok := h.findCurrentUser(c)
	if !ok {
		return
	}

	var req updateUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	updates := map[string]any{}

	if req.Username != nil {
		name := strings.TrimSpace(*req.Username)
		if len(name) < 3 || len(name) > 64 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "username length must be between 3 and 64"})
			return
		}
		updates["username"] = name
	}

	if req.Password != nil {
		if len(*req.Password) < 6 || len(*req.Password) > 128 {
			c.JSON(http.StatusBadRequest, gin.H{"error": "password length must be between 6 and 128"})
			return
		}
		hashed, err := security.HashPassword(*req.Password)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to hash password"})
			return
		}
		updates["password"] = hashed
	}

	if len(updates) == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no fields to update"})
		return
	}

	if err := h.DB.Model(&user).Updates(updates).Error; err != nil {
		if strings.Contains(strings.ToLower(err.Error()), "unique") {
			c.JSON(http.StatusConflict, gin.H{"error": "username already exists"})
			return
		}
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to update user"})
		return
	}

	if err := h.DB.First(&user, user.ID).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to reload user"})
		return
	}

	c.JSON(http.StatusOK, gin.H{"user": sanitizeUser(user)})
}

func (h *UserHandler) DeleteMe(c *gin.Context) {
	user, ok := h.findCurrentUser(c)
	if !ok {
		return
	}

	if err := h.DB.Delete(&user).Error; err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "failed to delete user"})
		return
	}

	c.Status(http.StatusNoContent)
}

func (h *UserHandler) findCurrentUser(c *gin.Context) (models.User, bool) {
	userID, ok := middleware.CurrentUserID(c)
	if !ok {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "missing user context"})
		return models.User{}, false
	}

	var user models.User
	if err := h.DB.First(&user, userID).Error; err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "user not found"})
		return models.User{}, false
	}

	return user, true
}

func sanitizeUser(user models.User) gin.H {
	return gin.H{
		"id":        user.ID,
		"username":  user.Username,
		"createdAt": user.CreatedAt,
		"updatedAt": user.UpdatedAt,
	}
}
