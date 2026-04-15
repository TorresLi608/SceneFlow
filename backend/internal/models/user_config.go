package models

import "gorm.io/gorm"

type UserConfig struct {
	gorm.Model
	UserID       uint   `gorm:"index;not null"`
	Purpose      string `gorm:"size:16;index;default:'script'"` // script | image | video
	Provider     string `gorm:"size:32;not null"`
	ModelName    string `gorm:"size:64"`
	EncryptedKey string `gorm:"type:text;not null"`
	IsActive     bool   `gorm:"default:false"`
}
