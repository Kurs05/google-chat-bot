<img width="632" height="208" alt="image" src="https://github.com/user-attachments/assets/48ad2548-1c8d-4c4c-9446-1d64c9be4a4c" />

# Document Chat Bot

A Google Chat bot that allows you to create polls for domain users and track voting results.

##  Tech Stack

- Python 3.11  
- Google Cloud Functions  
- Firestore (Cloud Firestore)  
- Gmail API  
- Google Chat API  
- Service accounts with OAuth and domain-wide delegation  

---

## Features of Document Chat Bot

**Document Chat Bot** is a corporate Google Chat bot designed to create internal domain polls with storage and processing of results in Firestore. It simplifies collecting feedback and automates user interaction via Google Chat and Gmail.

### Functional Capabilities:

- Create polls via Google Chat commands  <br>
  The bot supports a clear syntax to create polls with predefined answer options.

- Real-time vote handling and information updates  <br>
  The bot tracks user choices and updates data as users vote.

- Store and manage results in Firestore  <br>
  All poll data, including participant lists and their answers, is stored in Firestore.

- Notifications via Gmail API  <br>
  If needed, the bot can send poll results to poll creators by email.

- Operates using a service account with domain-wide delegation  <br>
  This allows acting on behalf of a user without requiring manual authorization.

- Integration with Secret Manager  <br>
  All sensitive data (like keys and settings) can be stored securely.

---

##  Installation and Setup

### 1. Clone the Project

```bash
git clone https://github.com/Kurs05/document-chat-bot.git
cd document-chat-bot
```

### 2. Project Structure  
Make sure the project includes both `requirements.txt` and `main.py`. Without them, Cloud Function will throw an error.

<img width="500" height="401" alt="image" src="https://github.com/user-attachments/assets/6f7a7d26-5554-469b-af68-d71ce9700207" />

### 3. Service Account Roles and Delegation

Assign the following roles (OAuth scopes) to the service account used by the bot:

```bash
["https://www.googleapis.com/auth/chat.bot", 
 "https://www.googleapis.com/auth/chat.messages.create",
 "https://www.googleapis.com/auth/gmail.send",
 "https://www.googleapis.com/auth/userinfo.email",
 "https://www.googleapis.com/auth/contacts.readonly"]
```

Also, domain-wide delegation must be enabled. Without it, the bot will not function.

---

### 4. Enabled APIs Required for Bot Functionality  
#### In *APIs & Services*:
-  People API  
-  Secret Manager API  
-  Gmail API  
-  Google Chat API  

---

### 5. Connect the Secret  
#### In *Secret Manager*  
Create a secret named `key_for_chat_service` and upload your service account's JSON key there.

---

## Bot Screenshots

1) Poll creation  
<img width="600" height="679" alt="image" src="https://github.com/user-attachments/assets/dd92ac77-c93d-4d4a-98f0-2e24e6aa9642" />

2) Poll closure  
<img width="600" height="679" alt="image" src="https://github.com/user-attachments/assets/2dcfc8e8-49ec-41c3-ad45-fa6cffef9ef6" />

3) If results are also sent via DM or email  
<img width="600" height="346" alt="image" src="https://github.com/user-attachments/assets/a03761eb-69fd-4627-a4b4-67f4fe6ae869" />

4) Example of what users receive  
<img width="600" height="500" alt="image" src="https://github.com/user-attachments/assets/2a05a0a7-fd88-4802-b712-e23c8442b681" />
