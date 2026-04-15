package database

import (
	"sceneflow/backend/internal/models"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

func Init(dbPath string) (*gorm.DB, error) {
	db, err := gorm.Open(sqlite.Open(dbPath), &gorm.Config{})
	if err != nil {
		return nil, err
	}

	if err := db.AutoMigrate(
		&models.User{},
		&models.UserConfig{},
		&models.Project{},
		&models.Scene{},
	); err != nil {
		return nil, err
	}

	return db, nil
}
