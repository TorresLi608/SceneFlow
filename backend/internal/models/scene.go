package models

import "gorm.io/gorm"

type Scene struct {
	gorm.Model
	ID           string `gorm:"primaryKey;size:80"`
	ProjectID    string `gorm:"index;size:80;not null"`
	OrderNum     int
	Narration    string `gorm:"type:text"`
	VisualPrompt string `gorm:"type:text"`
	ImageURL     string
	ImageStatus  string `gorm:"size:20;default:'idle'"`
	AudioURL     string
	AudioStatus  string `gorm:"size:20;default:'idle'"`
}
