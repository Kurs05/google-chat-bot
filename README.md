<img width="632" height="208" alt="image" src="https://github.com/user-attachments/assets/48ad2548-1c8d-4c4c-9446-1d64c9be4a4c" />

# Document Chat Bot

Бот для Google Chat, при помощи которого можно создавать опросы для пользователей внутри домена и отслеживать результаты голосования.

##  Стек технологий

- Python 3.11
- Google Cloud Functions
- Firestore (Cloud Firestore)
- Gmail API
- Google Chat API 
- Сервисные аккаунты с OAuth и делегированием

---
## Возможности Document Chat Bot
Document Chat Bot — это корпоративный бот для Google Chat, предназначенный для организации опросов внутри домена с сохранением и обработкой результатов в Firestore. Он упрощает сбор обратной связи и автоматизирует взаимодействие с пользователями через Google Chat и Gmail.

### Функциональные возможности:
- Создание опросов через команды в Google Chat  <br> Бот поддерживает понятный синтаксис для создания опросов с заранее заданными вариантами ответа.

- Обработка голосов и обновление информации в реальном времени <br> Бот отслеживает выбор пользователей и отображает обновлённые данные по мере голосования.

- Формирование и хранение результатов в Firestore <br> Все данные опросов, включая список участников и их ответы, сохраняются в Firestore.

- Уведомления через Gmail API <br> При необходимости бот может отправлять письма создателям опроса с результатом голосования.

- Работа с использованием сервисного аккаунта с делегированием на уровне домена <br> Это позволяет работать от имени пользователя без необходимости авторизации с его стороны.

- Интеграция с Secret Manager <br> Все чувствительные данные (например, ключи и настройки) могут храниться в безопасном виде.
##  Установка и настройка

### 1. Клонирование проекта

```bash
git clone https://github.com/Kurs05/document-chat-bot.git
cd document-chat-bot

```
### 2. Структура проекта 
   Необходимо, чтобы обязательно в проекте был файл requirements.txt и main.py , без них cloud_function выдаст ошибку.

<img width="500" height="401" alt="image" src="https://github.com/user-attachments/assets/6f7a7d26-5554-469b-af68-d71ce9700207" />

### 3. Права сервисного аккаунта и делегирование

  Сервисному аккаунту, который отвечает за данного чат-бота необходимо выдать роли:
  ```bash
  ["https://www.googleapis.com/auth/chat.bot", 
  "https://www.googleapis.com/auth/chat.messages.create",
  "https://www.googleapis.com/auth/gmail.send",
  "https://www.googleapis.com/auth/userinfo.email",
  "https://www.googleapis.com/auth/contacts.readonly"]
  ```
Также необходимо делегирование на уровне домена, без этого бот не заработает.

### 4. Какие сервисы необходимо подключить для работы бота:
 #### В APIs & Services
  - 1)People Api
  - 2)Secret Manager Api
  - 3)Gmail Api
  - 4)Google Chat Api

### 5. Подключение секрета
#### В Secret Manager
Создай секрет key_for_chat_service и загрузи JSON ключ сервисного аккаунта

## Скриншоты работы бота
1) при создании опроса
<img width="600" height="679" alt="image" src="https://github.com/user-attachments/assets/dd92ac77-c93d-4d4a-98f0-2e24e6aa9642" />

2) при завершении опроса
<img width="600" height="679" alt="image" src="https://github.com/user-attachments/assets/2dcfc8e8-49ec-41c3-ad45-fa6cffef9ef6" />

3) если отправлять также в личные сообщения или на почту результат опроса пользователям
   <img width="600" height="346" alt="image" src="https://github.com/user-attachments/assets/a03761eb-69fd-4627-a4b4-67f4fe6ae869" />

4) пример того,что приходит пользователям 
<img width="600" height="500" alt="image" src="https://github.com/user-attachments/assets/2a05a0a7-fd88-4802-b712-e23c8442b681" />


