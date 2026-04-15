package main

import (
	"log"
	"net/http"
	"time"

	"sceneflow/backend/internal/ai"
	"sceneflow/backend/internal/config"
	"sceneflow/backend/internal/database"
	"sceneflow/backend/internal/handlers"
	"sceneflow/backend/internal/middleware"
	"sceneflow/backend/internal/ws"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

func main() {
	cfg := config.Load()

	db, err := database.Init(cfg.DBPath)
	if err != nil {
		log.Fatalf("failed to initialize database: %v", err)
	}

	authHandler := &handlers.AuthHandler{DB: db, JWTSecret: cfg.JWTSecret}
	userHandler := &handlers.UserHandler{DB: db}
	parser := ai.NewParser()
	userConfigHandler := &handlers.UserConfigHandler{DB: db, AESKey: cfg.AESKey, Parser: parser}
	hub := ws.NewHub()
	projectHandler := &handlers.ProjectHandler{DB: db, AESKey: cfg.AESKey, Parser: parser, Hub: hub}
	projectWSHandler := &handlers.ProjectWSHandler{DB: db, JWTSecret: cfg.JWTSecret, Hub: hub}

	go hub.Run()

	router := gin.Default()
	router.Use(
		cors.New(
			cors.Config{
				AllowOrigins:     []string{"http://localhost:3000", "http://127.0.0.1:3000"},
				AllowMethods:     []string{"GET", "POST", "PATCH", "DELETE", "OPTIONS"},
				AllowHeaders:     []string{"Origin", "Content-Type", "Authorization"},
				AllowCredentials: true,
				MaxAge:           12 * time.Hour,
			},
		),
	)
	router.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})
	router.GET("/ws/projects/:id", projectWSHandler.ServeWS)

	api := router.Group("/api")
	{
		authGroup := api.Group("/auth")
		{
			authGroup.POST("/register", authHandler.Register)
			authGroup.POST("/login", authHandler.Login)
		}

		protected := api.Group("")
		protected.Use(middleware.JWTAuth(cfg.JWTSecret))
		{
			protected.GET("/users/me", userHandler.GetMe)
			protected.PATCH("/users/me", userHandler.UpdateMe)
			protected.DELETE("/users/me", userHandler.DeleteMe)

			protected.POST("/settings/keys", userConfigHandler.Create)
			protected.POST("/settings/keys/validate", userConfigHandler.Validate)
			protected.GET("/settings/keys", userConfigHandler.List)
			protected.GET("/settings/keys/:id", userConfigHandler.Get)
			protected.PATCH("/settings/keys/:id", userConfigHandler.Update)
			protected.DELETE("/settings/keys/:id", userConfigHandler.Delete)

			protected.POST("/projects/:id/parse", projectHandler.ParseProject)
			protected.POST("/projects/:id/optimize", projectHandler.OptimizeScript)
			protected.POST("/projects/:id/generate", projectHandler.GenerateProject)
			protected.POST("/projects/:id/generate-video", projectHandler.GenerateVideo)
			protected.DELETE("/projects/:id", projectHandler.DeleteProject)
		}
	}

	log.Printf("SceneFlow backend listening on :%s", cfg.Port)
	if err := router.Run(":" + cfg.Port); err != nil {
		log.Fatalf("server exited: %v", err)
	}
}
