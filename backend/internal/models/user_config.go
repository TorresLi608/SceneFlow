package models

import "gorm.io/gorm"

type UserConfig struct {
	gorm.Model
	UserID       uint   `gorm:"index;not null"`
	Provider     string `gorm:"size:32;not null"`
	EncryptedKey string `gorm:"type:text;not null"`
	IsActive     bool   `gorm:"default:false"`
}
