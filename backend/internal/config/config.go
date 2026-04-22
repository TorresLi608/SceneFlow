package config

import (
	"crypto/sha256"
	"os"
)

type Config struct {
	Port          string
	DBPath        string
	JWTSecret     string
	AESKey        []byte
	PublicBaseURL string
	GeneratedDir  string
}

func Load() Config {
	port := getenv("PORT", "8080")
	dbPath := getenv("SCENEFLOW_DB_PATH", "./sceneflow.db")
	jwtSecret := getenv("SCENEFLOW_JWT_SECRET", "dev-jwt-secret-change-me")
	publicBaseURL := getenv("SCENEFLOW_PUBLIC_BASE_URL", "http://127.0.0.1:8080")
	generatedDir := getenv("SCENEFLOW_GENERATED_DIR", "./generated")

	aesSource := getenv("SCENEFLOW_AES_KEY", "dev-aes-key-change-me")
	aesSum := sha256.Sum256([]byte(aesSource))

	return Config{
		Port:          port,
		DBPath:        dbPath,
		JWTSecret:     jwtSecret,
		AESKey:        aesSum[:],
		PublicBaseURL: publicBaseURL,
		GeneratedDir:  generatedDir,
	}
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
