-- Base de datos de una cuenta creada con la versión 1.9.0 (antes de los tableros),
-- con datos INVENTADOS: yoshi@test.com y otro@test.com, contraseña "secret123".
-- La usa tests/test_deploy.py para simular un deploy real: base vieja ->
-- scripts/migrate.py -> arranque de la versión actual.
BEGIN TRANSACTION;
CREATE TABLE habit_entries (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	entry_date DATE NOT NULL, 
	habits_data JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE habits (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	"key" VARCHAR NOT NULL, 
	label VARCHAR NOT NULL, 
	icon VARCHAR, 
	color VARCHAR, 
	"order" INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE pomodoro_sessions (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	project_id INTEGER, 
	task_id INTEGER, 
	session_date DATE NOT NULL, 
	started_at DATETIME NOT NULL, 
	ended_at DATETIME NOT NULL, 
	duration_seconds INTEGER NOT NULL, 
	planned_seconds INTEGER NOT NULL, 
	mode VARCHAR NOT NULL, 
	was_completed BOOLEAN NOT NULL, 
	note VARCHAR, 
	source VARCHAR NOT NULL, 
	created_at DATE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id)
);
INSERT INTO "pomodoro_sessions" VALUES(1,1,1,1,'2026-09-22','2026-09-22 15:34:24.071063','2026-09-22 19:34:24.071063',14400,1500,'focus',1,NULL,'timer','2026-09-22');
INSERT INTO "pomodoro_sessions" VALUES(2,1,1,2,'2026-09-22','2026-09-22 19:09:24.071063','2026-09-22 19:34:24.071063',1500,1500,'focus',1,NULL,'timer','2026-09-22');
INSERT INTO "pomodoro_sessions" VALUES(3,1,1,3,'2026-09-22','2026-09-22 18:59:24.071063','2026-09-22 19:34:24.071063',2100,1500,'focus',1,NULL,'timer','2026-09-22');
INSERT INTO "pomodoro_sessions" VALUES(4,1,1,4,'2026-09-22','2026-09-22 17:37:24.071063','2026-09-22 19:34:24.071063',7020,1500,'focus',1,NULL,'timer','2026-09-22');
CREATE TABLE projects (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	description VARCHAR, 
	color VARCHAR, 
	icon VARCHAR, 
	"order" INTEGER NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_projects_user_name UNIQUE (user_id, name), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
INSERT INTO "projects" VALUES(1,1,'Habit Tracker',NULL,'#3498db',NULL,0,1,'2026-09-22');
INSERT INTO "projects" VALUES(2,1,'Archivado',NULL,NULL,NULL,0,0,'2026-09-22');
INSERT INTO "projects" VALUES(3,2,'Ajeno',NULL,NULL,NULL,0,1,'2026-09-22');
CREATE TABLE tasks (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	project_id INTEGER NOT NULL, 
	title VARCHAR NOT NULL, 
	notes VARCHAR, 
	is_done BOOLEAN NOT NULL, 
	"order" INTEGER NOT NULL, 
	completed_at DATE, 
	created_at DATE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id)
);
INSERT INTO "tasks" VALUES(1,1,1,'Corrección de Pomodoros',NULL,1,0,'2026-09-22','2026-09-22');
INSERT INTO "tasks" VALUES(2,1,1,'Confirmación de cambios datos y cancelación pomodoro',NULL,1,0,'2026-09-22','2026-09-22');
INSERT INTO "tasks" VALUES(3,1,1,'Confirmación de guardado de datos en hábitos',NULL,1,0,'2026-09-22','2026-09-22');
INSERT INTO "tasks" VALUES(4,1,1,'modificación de tiempo de pomodoros',NULL,1,0,'2026-09-22','2026-09-22');
INSERT INTO "tasks" VALUES(5,1,1,'Revisión de idea para cambiar a kanban',NULL,0,0,NULL,'2026-09-22');
INSERT INTO "tasks" VALUES(6,2,3,'Tarea ajena',NULL,0,0,NULL,'2026-09-22');
CREATE TABLE users (
	id INTEGER NOT NULL, 
	email VARCHAR NOT NULL, 
	hashed_password VARCHAR NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	display_name VARCHAR, 
	first_name VARCHAR, 
	last_name VARCHAR, 
	rest_days JSON NOT NULL, 
	PRIMARY KEY (id)
);
INSERT INTO "users" VALUES(1,'yoshi@test.com','$2b$12$ke3E/2yD7JgRLNkRfIBbCOKXOPPmiR/wE/SpdYYRKViWGbbfiXobS',1,NULL,NULL,NULL,'[]');
INSERT INTO "users" VALUES(2,'otro@test.com','$2b$12$nOqEkxWrzsmWBvHX49nNYO6RmGFNkLPs14AfNPYtL4Ugk7DFIgFyW',1,NULL,NULL,NULL,'[]');
CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE INDEX ix_habit_entries_entry_date ON habit_entries (entry_date);
CREATE INDEX ix_habits_key ON habits ("key");
CREATE INDEX ix_habits_user_id ON habits (user_id);
CREATE INDEX ix_projects_user_id ON projects (user_id);
CREATE INDEX ix_tasks_user_id ON tasks (user_id);
CREATE INDEX ix_tasks_project_id ON tasks (project_id);
CREATE INDEX ix_pomodoro_sessions_mode ON pomodoro_sessions (mode);
CREATE INDEX ix_pomodoro_sessions_task_id ON pomodoro_sessions (task_id);
CREATE INDEX ix_pomodoro_sessions_source ON pomodoro_sessions (source);
CREATE INDEX ix_pomodoro_sessions_user_id ON pomodoro_sessions (user_id);
CREATE INDEX ix_pomodoro_sessions_project_id ON pomodoro_sessions (project_id);
CREATE INDEX ix_pomodoro_sessions_session_date ON pomodoro_sessions (session_date);
COMMIT;
