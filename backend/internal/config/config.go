package config

import (
	"crypto/sha256"
	"os"
)

type Config struct {
	Port      string
	DBPath    string
	JWTSecret string
	AESKey    []byte
}

func Load() Config {
	port := getenv("PORT", "8080")
	dbPath := getenv("SCENEFLOW_DB_PATH", "./sceneflow.db")
	jwtSecret := getenv("SCENEFLOW_JWT_SECRET", "dev-jwt-secret-change-me")

	aesSource := getenv("SCENEFLOW_AES_KEY", "dev-aes-key-change-me")
	aesSum := sha256.Sum256([]byte(aesSource))

	return Config{
		Port:      port,
		DBPath:    dbPath,
		JWTSecret: jwtSecret,
		AESKey:    aesSum[:],
	}
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}
