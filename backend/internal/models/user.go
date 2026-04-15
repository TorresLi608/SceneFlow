package models

import "gorm.io/gorm"

type User struct {
	gorm.Model
	Username string       `gorm:"uniqueIndex;size:64;not null"`
	Password string       `gorm:"not null"`
	Configs  []UserConfig `gorm:"constraint:OnDelete:CASCADE"`
}
