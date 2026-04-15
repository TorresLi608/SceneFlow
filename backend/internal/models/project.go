package models

import "gorm.io/gorm"

type Project struct {
	gorm.Model
	ID             string  `gorm:"primaryKey;size:80"`
	UserID         uint    `gorm:"index;not null"`
	OriginalScript string  `gorm:"type:text"`
	Status         string  `gorm:"size:20;default:'idle'"`
	Scenes         []Scene `gorm:"foreignKey:ProjectID;constraint:OnDelete:CASCADE"`
}
