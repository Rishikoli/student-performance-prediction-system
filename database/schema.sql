-- MySQL schema for the Student Performance Management and Prediction System
-- Generated from app/models.py. `python seed.py` creates these tables automatically;
-- this file is provided for reference / manual setup.

CREATE DATABASE IF NOT EXISTS student_performance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE student_performance;

CREATE TABLE students (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	roll_no VARCHAR(20) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	school ENUM('GP','MS') NOT NULL, 
	sex ENUM('F','M') NOT NULL, 
	age INTEGER NOT NULL, 
	address ENUM('U','R') NOT NULL, 
	famsize ENUM('LE3','GT3') NOT NULL, 
	`Pstatus` ENUM('T','A') NOT NULL, 
	`Medu` INTEGER NOT NULL, 
	`Fedu` INTEGER NOT NULL, 
	`Mjob` VARCHAR(20) NOT NULL, 
	`Fjob` VARCHAR(20) NOT NULL, 
	reason VARCHAR(20) NOT NULL, 
	nursery BOOL NOT NULL, 
	internet BOOL NOT NULL, 
	created_at DATETIME, 
	PRIMARY KEY (id)
) ENGINE=InnoDB;

CREATE TABLE subjects (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	code VARCHAR(10) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (code)
) ENGINE=InnoDB;

CREATE TABLE academic_records (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	student_id INTEGER NOT NULL, 
	subject_id INTEGER NOT NULL, 
	guardian VARCHAR(10) NOT NULL, 
	traveltime INTEGER NOT NULL, 
	studytime INTEGER NOT NULL, 
	failures INTEGER NOT NULL, 
	schoolsup BOOL NOT NULL, 
	famsup BOOL NOT NULL, 
	paid BOOL NOT NULL, 
	activities BOOL NOT NULL, 
	higher BOOL NOT NULL, 
	romantic BOOL NOT NULL, 
	famrel INTEGER NOT NULL, 
	freetime INTEGER NOT NULL, 
	goout INTEGER NOT NULL, 
	`Dalc` INTEGER NOT NULL, 
	`Walc` INTEGER NOT NULL, 
	health INTEGER NOT NULL, 
	absences INTEGER NOT NULL, 
	`G1` INTEGER, 
	`G2` INTEGER, 
	`G3` INTEGER, 
	assignment_score FLOAT, 
	practical_score FLOAT, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (student_id, subject_id), 
	FOREIGN KEY(student_id) REFERENCES students (id), 
	FOREIGN KEY(subject_id) REFERENCES subjects (id)
) ENGINE=InnoDB;

CREATE TABLE users (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	username VARCHAR(50) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	full_name VARCHAR(100) NOT NULL, 
	`role` ENUM('admin','teacher','student') NOT NULL, 
	subject_id INTEGER, 
	student_id INTEGER, 
	is_active_user BOOL, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(subject_id) REFERENCES subjects (id), 
	FOREIGN KEY(student_id) REFERENCES students (id)
) ENGINE=InnoDB;

CREATE TABLE attendance (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	record_id INTEGER NOT NULL, 
	date DATE NOT NULL, 
	status ENUM('present','absent') NOT NULL, 
	marked_by INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (record_id, date), 
	FOREIGN KEY(record_id) REFERENCES academic_records (id), 
	FOREIGN KEY(marked_by) REFERENCES users (id)
) ENGINE=InnoDB;

CREATE TABLE predictions (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	record_id INTEGER NOT NULL, 
	feature_set VARCHAR(10) NOT NULL, 
	predicted_g3 FLOAT NOT NULL, 
	predicted_grade VARCHAR(2) NOT NULL, 
	pass_probability FLOAT NOT NULL, 
	risk_level VARCHAR(10) NOT NULL, 
	model_info VARCHAR(100), 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(record_id) REFERENCES academic_records (id)
) ENGINE=InnoDB;

CREATE UNIQUE INDEX ix_students_roll_no ON students (roll_no);
CREATE UNIQUE INDEX ix_users_username ON users (username);
