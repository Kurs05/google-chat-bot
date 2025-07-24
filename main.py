import mimetypes
import os
import tempfile
from dataclasses import dataclass
from email.utils import encode_rfc2231
from typing import Any, Mapping, cast, TextIO,Dict, Any
import functions_framework
from flask import request, jsonify, send_file, abort, url_for
from googleapiclient import discovery
from google.oauth2 import service_account
import json
import logging
import io

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.http import MediaFileUpload
from google.cloud import firestore
from urllib.parse import quote, urlparse

import base64
from googleapiclient.discovery import build
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from jinja2 import Template

from dataclasses import dataclass, asdict
from typing import Optional
import re
from google.cloud import secretmanager


def access_secret_version(secret_id: str, project_id: str, version_id: str = "latest") -> str:
    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    response = client.access_secret_version(name=secret_name)
    return response.payload.data.decode("UTF-8")
# подставляем свое название секрета и id проекта
SERVICE_ACCOUNT_FILE = json.loads(access_secret_version('key_for_chat_service',111111111111))

db = firestore.Client.from_service_account_info(SERVICE_ACCOUNT_FILE)

SCOPESv1 = ["https://www.googleapis.com/auth/chat.bot"]
credsv1 = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_FILE, scopes=SCOPESv1)

SCOPESv2 = ["https://www.googleapis.com/auth/chat.messages.create","https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/userinfo.email","https://www.googleapis.com/auth/contacts.readonly"]
credsv2 = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_FILE, scopes=SCOPESv2)
delegated_credentials = credsv2.with_subject("document.bot@yourcompany.com")

chat_service = discovery.build("chat", "v1", credentials=credsv1)
base_url = os.getenv("BASE_URL")
SPACE_GROUP = os.getenv("GROUP_SPACE_ID")
logging.basicConfig(
    level=logging.INFO,
    encoding="utf-8",
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("chatbot.log"),  # Записываем логи в файл
        logging.StreamHandler()  # Также выводим логи в консоль
    ]
)
GOOGLE_DOMAINS = [
    "drive.google.com",
    "docs.google.com",
    "sheets.google.com",
    "slides.google.com",
]
URL_PATTERN = r"https?://[^\s]+"

def is_url(message: str):

    matches = re.findall(URL_PATTERN, message)

    for url in matches:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        if any(domain.endswith(allowed) for allowed in GOOGLE_DOMAINS):
            return url
    return None



@dataclass
class Attachment:
    content: Optional[str] = None
    file: Optional[str] = None
    name: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """Создает объект Attachment из словаря"""
        return cls(**data) if data else None
@dataclass
class UrlData:
    link: Optional[str] = None


    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """Создает объект Attachment из словаря"""
        return cls(**data) if data else None
@dataclass
class Quiz:
    attachment: Optional[Attachment] = None
    url_link: Optional[UrlData] = None
    sender_name: Optional[str] = None
    sender_space: Optional[str] = None
    sender_display_name: Optional[str] = None
    final_user: Optional[str] = None
    final_user_name: Optional[str] = None
    quiz_name: Optional[str] = None
    quiz_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """Создает объект Quiz из словаря, автоматически создавая вложенные объекты"""
        return cls(
            attachment=Attachment.from_dict(data.get("attachment")),
            url_link=UrlData.from_dict(data.get("url_link")),
            sender_name=data.get("sender_name"),
            sender_space=data.get("sender_space"),
            sender_display_name=data.get("sender_display_name"),
            final_user=data.get("final_user"),
            quiz_name=data.get("quiz_name"),
            quiz_id=data.get("quiz_id"),
            final_user_name=data.get("final_user_name")
        )


def get_url(base_url,attachment_name,content_name,file_name):
    return f"{base_url}?attachment_name={attachment_name}&content_name={content_name}&file_name={file_name}"

def download_url(request):
    file_content = request.args.get('content_name')
    attachment_file = request.args.get('attachment_name')
    attachment_name = request.args.get('file_name')
    file = download_file(attachment_file, file_content)
    file_name = file.get("file")
    if not attachment_file and file_content:
        abort(400, "Не указан file_path или file_content")

    response = send_file(
        file_name,
        as_attachment=False,
        mimetype=file_content
    )
    # Устанавливаем имя файла через заголовок Content-Disposition

    encoded_filename = quote(attachment_name, safe='', encoding="utf-8")
    response.headers["Content-Disposition"] = f'inline; filename="{encoded_filename}";filename*=UTF-8\'\'{encoded_filename}'
    return response

CLICK_COMMANDS ={}

def command_route(command):
    def decorator(func):
        CLICK_COMMANDS[command]=func
        return func
    return decorator

@functions_framework.http
def chatbot(request):
    file_content = request.args.get('content_name')
    attachment_file = request.args.get('attachment_name')
    if file_content and attachment_file:
        return download_url(request)
    else:
        return handle_chat(request)


def handle_chat(request):
    """Обрабатывает HTTP-запросы от Google Chat."""

    request_json = request.get_json(silent=True)

    if request_json is None:
        logging.warning(" request_json is None! Возможно, пришел пустой запрос.")
        logging.warning(f"Request method: {request.method}")
        logging.warning(f"Args: {request.args}")
        return {"text": "Ошибка: пустой запрос."}

    logging.info(json.dumps({"Точка вхождения": request_json}, ensure_ascii=False, indent=2))

    has_attachment = "attachment" in request_json.get("message", {})
    has_url = is_url(request_json["message"].get("text",""))

    if has_url or has_attachment:
        return create_quiz_card(request_json, has_url if has_url else None)

    def choice_type(command, request_json):
        if command:
            return CLICK_COMMANDS[command](request_json)

    match request_json.get("type"):
        case "CARD_CLICKED":
            command= request_json.get("common").get("invokedFunction")
            body = choice_type(command,request_json)
            return body
        case "MESSAGE":
            command= request_json.get("message").get("slashCommand").get("commandId")
            body = choice_type(command,request_json)
            return body
        case _:
            return {}



# def save_space(event:dict):
#     space = event.get("message").get("space").get("name")
#     name = event.get("user", {}).get("name")
#     # добавляем в бд данные о спэйсе нашем
#     if space is not None:
#
#
#         replaced_name = name.replace("/", "_").strip()
#         doc_ref = db.collection("Space").document(replaced_name)
#         doc_ref.set({
#             "space": space
#         })
#     return {}

def create_quiz_card(event:dict,url):

    if not url:
        resource_name = event.get("message").get("attachment")[0].get("attachmentDataRef").get(
            "resourceName")
        content_name = event.get("message").get("attachment")[0].get("contentType")
        file_name =  event.get("message").get("attachment")[0].get("contentName")

        attachment = {"content":content_name,"file":resource_name,"name":file_name}
        quiz= Quiz.from_dict({"attachment":attachment})
    else:
        url= {"link":url}
        quiz= Quiz.from_dict({"url_link":url})

    return {
        "cardsV2": [{
            "cardId": "participants",
            "card": {
                "header": {"title": "Опрос"},
                "sections": [{
                    "widgets":
                        [   {"textParagraph": {"text": "Придумайте название опроса:"}},
                            {
                                "textInput": {
                                    "label": "Название",
                                    "type": "SINGLE_LINE",
                                    "name": "quiz_name"
                                }
                            },
                            {
                                "divider": {}
                            },
                            {"textParagraph": {"text": "Выберите участников опроса:"}},
                            {
                                "divider": {}
                            },
                            {
                                "selectionInput": {
                                    "name": "contacts",
                                    "type": "MULTI_SELECT",
                                    "label": "Участники опроса",
                                    "multiSelectMaxSelectedItems": 20,
                                    "multiSelectMinQueryLength": 1,
                                    "platformDataSource": {
                                        "commonDataSource": "USER"
                                    }
                                }
                            },
                            {"textParagraph": {"text": "Выберите конечного получателя :"}},
                            {
                                "selectionInput": {
                                    "name": "contact",
                                    "type": "MULTI_SELECT",
                                    "label": "Конечный получатель",
                                    "multiSelectMaxSelectedItems": 1,
                                    "multiSelectMinQueryLength": 1,
                                    "platformDataSource": {
                                        "commonDataSource": "USER"
                                    }
                                }
                            },
                            {
                                "buttonList": {
                                    "buttons": [{
                                        "text": "Отправить",
                                        "onClick": {
                                            "action": {
                                                "function": "finish_func",
                                                "parameters":[
                                                    {"key":"quiz","value":json.dumps(asdict(quiz))},

                                                ]

                                            }
                                        }
                                    }]
                                }
                            }
                        ]
                }]
            }
        }]
    }

@command_route("2")
def create_about_card(request_json):
    """Создает карточку с запросом участников"""
    return {"privateMessageViewer": {"name": f'{request_json.get("user").get("name")}'},
            "cardsV2": [{
                "cardId": "quiz_setup",
                "card": {
                    "header": {"title": "Создание опроса"},
                    "sections": [{
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": "Вы можете создать опрос отправив боту файл в виде вложения либо какой-либо гугл-ссылки"
                                }
                            }
                        ]
                    }]
                }
            }]
            }


@command_route("finish_func")
def finish_func(event: dict):
    sender_name = event.get("user", {}).get("name")
    sender_space = event.get('message').get('space').get('name')
    replaced_name = sender_name.replace("/", "_").strip()
    sender_display_name = event.get("user", {}).get("displayName")
    users = event.get("common").get("formInputs").get("contacts").get("stringInputs").get("value")
    final_user = event.get("common").get("formInputs").get("contact",{}).get("stringInputs",{}).get("value",[None])[0]
    quiz_name = event.get("common").get("formInputs").get("quiz_name").get("stringInputs").get("value")[0]

    params = event.get("common", {}).get("parameters", {})
    quiz_json = json.loads(params.get("quiz"))
    quiz = Quiz.from_dict({**quiz_json, "sender_name": sender_name, "sender_space": sender_space,
                   "sender_display_name": sender_display_name, "final_user": final_user,
                   "quiz_name": quiz_name})

    if quiz.attachment:
        attachment=quiz.attachment
        url = get_url(base_url, attachment.file, attachment.content, attachment.name)
    elif quiz.url_link:
        url_link= quiz.url_link
        url= url_link.link

    def create_button(text, state, open_dialog=False):
        button = {
            "text": text,
            "onClick": {
                "action": {
                    "function": "user_action",
                    "parameters": [
                        {"key": "user_sender", "value": replaced_name},
                        {"key": "user", "value": user.replace("/", "_").strip()},
                        {"key": "quiz", "value": json.dumps(asdict(quiz))},
                        {"key": "state", "value": str(state)},
                    ]
                }
            }
        }
        if open_dialog:
            button["onClick"]["action"]["interaction"] = "OPEN_DIALOG"
        return button

    quiz.quiz_id = upload_to_fire(replaced_name, users,quiz)
    for user in users:
        buttons = [
            create_button("Отклонить", False,  open_dialog=True),
            create_button("Подтвердить", True)
        ]
        message = {
            "cardsV2": [{
                "cardId": "user_card",
                "card": {
                    "header": {"title": f"Опрос {quiz_name}"},
                    "sections": [{
                        "widgets": [
                            {
                                "textParagraph": {
                                    "text": f"Опрос создал <b>{sender_display_name}</b>"
                                }
                            },
                            {
                                "divider": {}
                            },
                            {
                                "textParagraph": {
                                    "text": "Просмотрите содержимое файла и выберите Отклонить/Подтвердить>"
                                }
                            },
                            {
                                "divider": {}
                            },
                            {
                                "buttonList": {
                                    "buttons": [{
                                        "text": "Открыть файл",
                                        "onClick": {
                                            "openLink": {
                                                "url": url
                                            }
                                        }
                                    }]
                                }
                            },
                            {
                                "divider": {}
                            },
                            {
                                "textParagraph": {
                                    "text": "Вы подтверждате? "
                                }
                            },
                            {"buttonList": {"buttons": buttons}}

                        ]
                    }]
                }
            }]}
        send_message(message,user)

    message = {
            "text": f"Вы успешно создали опрос *{quiz_name}* !"
            }

    response = chat_service.spaces().messages().create(
        parent= sender_space,
        body=message
    ).execute()

    quiz_message_name = response.get("name")
    doc_ref = db.collection("User_quizs").document(replaced_name)
    quiz_ref = doc_ref.collection("Quizs").document(quiz.quiz_id)
    quiz_ref.set({"quiz_message_name":quiz_message_name},merge=True)

    chat_service.spaces().messages().delete(name=event.get("message").get("name")).execute()
    return {}


def download_file(name, content):
    extension = mimetypes.guess_extension(content) if content else ""
    if not extension:
        logging.warning("Не удалось определить расширение для contentType: %s", content)

    req = chat_service.media().download_media(resourceName=name)
    file_io = io.BytesIO()
    downloader = MediaIoBaseDownload(file_io, req)

    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status.total_size:
            logging.info(f"Total size: {status.total_size} bytes")
        logging.info(f"Download {int(status.progress() * 100)}% complete")

    with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp_file:
        tmp_file.write(file_io.getvalue())
        tmp_file_path = tmp_file.name

    file_size = len(file_io.getvalue())
    logging.info(f" Временный файл успешно создан: {tmp_file_path}, размер: {file_size} байт")
    return {"file": tmp_file_path, "mime": content}

def upload_to_fire(name, users,quiz):
    doc_ref = db.collection("User_quizs").document(name)
    quiz_ref = doc_ref.collection("Quizs").document()
    if quiz.attachment:
        attachment=quiz.attachment
        quiz_ref.set(
            {
                "file_attachment": attachment.file,
                "file_content_name": attachment.content,
                "file_name": attachment.name,
            },merge=True
        )
    elif quiz.url_link:
        url_link= quiz.url_link
        quiz_ref.set(
            {
                "url_link":url_link.link
            },merge=True
        )
    quiz_ref.set(
        {
            "total": len(users),
            "answered": 0,
            "quiz_name": quiz.quiz_name,
            "final_user":quiz.final_user,
            "final_user_name":None,
            "sender_display_name":quiz.sender_display_name
        },merge=True
    )
    for user in users:
        user_name = user.replace("/", "_").strip()
        user_quiz = quiz_ref.collection("Users").document(user_name)
        user_quiz.set({"state": None})
    return quiz_ref.id

@command_route("user_action")
def user_action(event: dict):
    # достаем из параметров данные ,чтобы потом залезть в бд
    params = event.get("common", {}).get("parameters", {})
    quiz_json = json.loads(params.get("quiz"))
    quiz = Quiz.from_dict(quiz_json)
    user = params.get("user")
    state = params.get("state")
    user_sender = params.get("user_sender")#это replaced_name
    # Если state приходит как строка "True"/"False", можно привести к булевому значению:
    if isinstance(state, str):
        state = state.lower() == "true"

    # Проверяем, что это кнопка для отказа и нет введённых данных
    if not state and not event.get("common", {}).get("formInputs", {}).get("rejection_comment"):
        return {
            "actionResponse":
                {"type": "DIALOG",
                 "dialogAction": {
                     "dialog": {
                         "body": {
                             "sections": [{
                                 "header": "Форма для отклонения",
                                 "widgets": [

                                     {
                                         "textInput": {
                                             "label": "Введите причину отклонения",
                                             "type": "MULTIPLE_LINE",
                                             "name": "rejection_comment",
                                             "placeholderText": "*Оставить пустым*"
                                         },
                                     },
                                     {"buttonList": {"buttons": [
                                         {
                                             "text": "Отправить",
                                             "onClick": {
                                                 "action": {
                                                     "function": "user_action",
                                                     "parameters": [
                                                        {"key": "user_sender", "value": user_sender},
                                                        {"key": "user", "value": user},
                                                        {"key": "quiz", "value": json.dumps(asdict(quiz))},
                                                        {"key": "state", "value": str(state)},

                                                    ]

                                                 }
                                             }
                                         }
                                     ]}
                                     }
                                     , ]
                             }],
                         }
                     }
                 }
                 },

        }
    reason = event.get("common", {}).get("formInputs", {}).get("rejection_comment", {}).get("stringInputs", {}).get("value",[""])[0]

    doc_ref = db.collection("User_quizs").document(user_sender)
    quiz_ref = doc_ref.collection("Quizs").document(quiz.quiz_id)
    data = quiz_ref.get().to_dict()

    answered = data.get("answered")+1
    quiz_ref.update({"answered": firestore.Increment(1)})
    user_ref = quiz_ref.collection("Users").document(user)
    user_ref.set({"state": state, "reason": reason if not state else None}, merge=True)

    updated_doc = quiz_ref.get()
    data = updated_doc.to_dict()
    message_name=data.get('quiz_message_name')
    quiz_name = quiz.quiz_name
    users_dict=counting_users(user_sender,quiz.quiz_id)

    unanswered_users = format_users_dict(users_dict['unanswered'])
    widget=[{"textParagraph": {
        "text": f"*Пользователи, что еще не ответили*\n{unanswered_users}" if unanswered_users else "—"}}
    ]
    card=card_about_users(users_dict,quiz_name,widget)
    update_message(message_name,card,"text,cardsV2")

    total = data.get("total")
    members = get_members()

    final_user_name = ""
    if quiz.final_user in members:
        final_user_name = members[quiz.final_user]

    quiz.final_user_name = final_user_name
    # Если все участники ответили, выполняем дальнейшие действия
    if answered == total:
        negative_users = users_dict['negative']
        if quiz.final_user:

            #создаем кнопки куда закидываем инфу ,если есть отклонившие
            if negative_users:

                def create_button(text, state):
                    button = {
                        "text": text,
                        "onClick": {
                            "action": {
                                "function": "send_to_final_user",
                                "parameters": [
                                    {"key": "quiz", "value": json.dumps(asdict(quiz))},
                                    {"key": "state", "value": str(state)},
                                    {"key": "update", "value": "True"}
                                ]
                            }
                        }
                    }
                    return button
                buttons = [
                    create_button("Отправить", True),
                    create_button("Не отправлять", False)
                ]

                message = {
                    "cardsV2": [{
                        "cardId": "sender_to_final_card",
                        "card": {
                            "header": {"title": f"ЗАВЕРШЕН ОПРОС :{quiz_name}"},
                            "sections": [{
                                "widgets": [
                                    {
                                        "textParagraph": {
                                            "text": f"Желаете ли вы отправить файл <b>{final_user_name }</b> ?"
                                        }
                                    },
                                    {
                                        "divider": {}
                                    },
                                    {"buttonList": {"buttons": buttons}}

                                ]
                            }]
                        }
                    }]}
                send_message(message, user_sender.replace("_", "/").strip())

            #сразу отправляем
            else:
                state=True
                send_to_final_user(None,state,quiz)
        else:
            def create_button(text, state):
                button = {
                    "text": text,
                    "onClick": {
                        "action": {
                            "function": "create_user_widget",
                            "parameters": [
                                {"key": "state", "value": str(state)},
                                {"key": "quiz", "value": json.dumps(asdict(quiz))}

                            ]
                        }
                    }
                }
                return button

            buttons = [
                create_button("Отправить на почту", True),
                create_button("Отправить в ЛС", False)
            ]
            card = {
                    "cardsV2": [{
                        "cardId": "sender_to_final_card2",
                        "card": {
                            "header": {"title": f"ЗАВЕРШЕН ОПРОС :{quiz.quiz_name}"},
                            "sections": [{
                                "widgets": [
                                {
                                    "textParagraph": {
                                        "text": "Желаете ли вы отправить результат опроса пользователям?"
                                    }
                                },
                                {
                                    "buttonList": {
                                        "buttons": buttons
                                    }
                                }
                                ]
                            }]
                        }
                    }]}
            send_message(card,quiz.sender_name)
    return {'actionResponse': {'type': "UPDATE_MESSAGE"},
        "text": f"Спасибо за ваш ответ!"}

@command_route("send_to_final_user")
def send_to_final_user( event: dict = None,state=None,quiz=None,update=None):
    if event:
        params = event.get("common", {}).get("parameters", {})
        quiz_json= json.loads(params.get("quiz"))
        quiz=Quiz.from_dict(quiz_json)
        state = params.get("state")
        update = params.get("update",{})

    if quiz.attachment:
        attachment = quiz.attachment
        url = get_url(base_url, attachment.file, attachment.content, attachment.name)
    elif quiz.url_link:
        url_link=quiz.url_link
        url = url_link.link

    def card_return(text):
        card = {'actionResponse': {'type': "UPDATE_MESSAGE"} if update else {},
                "cardsV2": [{
                    "cardId": "sender_to_final_card2",
                    "card": {
                        "header": {"title": f"ЗАВЕРШЕН ОПРОС :{quiz.quiz_name}"},
                        "sections": [{
                            "widgets": [
                                {
                                    "textParagraph": {
                                        "text": text
                                    }
                                },

                            ]
                        }]
                    }
                }]}
        return card
    # Если state и update приходит как строка "True"/"False", приводим к булеву значению:
    if isinstance(state, str):
        state = state.lower() == "true"
    if isinstance(update, str):
        update = update.lower() == "true"
    replaced_name =quiz.sender_name.replace("/", "_").strip()
    users_dict = counting_users(replaced_name,quiz.quiz_id)

    #начальные виджеты
    start_widget =[
        {"textParagraph": {
            "text": f"Опрос создал <b>{quiz.sender_display_name}</b>"}
        }
        ,
        {
            "divider": {}
        }
    ]
    end_widgets = [
        {
            "divider": {}
        },
        {
            "textParagraph": {
                "text": "Просмотрите содержимое файла "
            }
        },

        {
            "buttonList": {
                "buttons": [{
                    "text": "Открыть файл",
                    "onClick": {
                        "openLink": {
                            "url": url
                        }
                    }
                }]
            }
        },
    ]
    #проверяем на Инпуты формы
    users = (event.get("common", {}).get("formInputs", {}).get("contacts", {}).get("stringInputs", {}).get("value")
        if event else None
    )
    if users:
        list_names = []
        members = get_members()
        users_dict = {
            'possitive': users_dict.get('possitive',[])+(users_dict.get('negative',[]))
                }

        for user in users:
            if user in members:
                list_names.append(members[user])
        names = " ,".join(name for name in list_names)
        #если нажали на кнопку На почту
        if state:
            people_service = build("people", "v1", credentials=delegated_credentials)
            for user in users:

                # запрос для поиска user_gmail
                user_id= user.replace("users/","")
                person = people_service.people().get(
                    resourceName=f"people/{user_id}",
                    personFields="emailAddresses"
                ).execute()
                # Получение e-mail юзера
                email = person.get("emailAddresses", [{}])[0].get("value")

                send_to_gmail(email,users_dict,quiz)
                    #так как name юзеров ищет в группе, то если пользака там нет ,то и имени нет :)
            text = f"Результат опроса *{quiz.quiz_name}* был отправлен пользователям *{names}* на почту "
            return {
                'actionResponse': {'type': "UPDATE_MESSAGE"},
                'text':text}
        #если нажата кнопка отправки в лс
        else:
            start_widget.extend([
                {"textParagraph": {
                    "text": f"Результат опроса отправил <b>{quiz.final_user_name or quiz.sender_display_name}</b>"}
                }
                ,
                {
                    "divider": {}
                }
            ])
            for user in users:

                card = card_about_users(users_dict, quiz.quiz_name, end_widgets, start_widget)
                send_message(card, user)
            text = f"Результат опроса *{quiz.quiz_name}* был отправлен пользователям *{names}* в личные сообщения "
            return {
                'actionResponse': {'type': "UPDATE_MESSAGE"},
                'text': text}

    if state :

        def create_button(text, state):
            button = {
                "text": text,
                "onClick": {
                    "action": {
                        "function": "create_user_widget",
                        "parameters": [
                            {"key": "state", "value": str(state)},
                            {"key": "quiz","value":json.dumps(asdict(quiz))}

                        ]
                    }
                }
            }
            return button

        buttons = [
            create_button("Отправить на почту", True),
            create_button("Отправить в ЛС", False)
        ]
        end_widgets.extend( [{
                "divider": {}
            },
            {
                "textParagraph": {
                    "text": "Желаете ли вы отправить результат опроса пользователям?"
                }
            },
            {"buttonList": {"buttons": buttons}}])
        #создаем карту и потом отправляем конечному пользаку
        card=card_about_users(users_dict,quiz.quiz_name,end_widgets,start_widget)

        send_message(card,quiz.final_user)

        text=f"Вы отправили файл конечному пользователю <b>{quiz.final_user_name}</b> "

        if event:
            return card_return(text)
        else:
            send_message(card_return(text),quiz.sender_name)
    else:
        text= f"Вы решили не отправлять файл"

        return card_return(text)

@command_route("create_user_widget")
def create_user_widget(event:dict):
    params = event.get("common", {}).get("parameters", {})
    state = params.get("state")
    quiz_json= params.get("quiz")

    if isinstance(state, str):
        state = state.lower() == "true"
    if state:
        text="На почту"
    else:
        text="В ЛС"
    return {
        "cardsV2": [{
            "cardId": "create_user_widget",
            "card": {
                "header": {"title": "Выбор пользователей"},
                "sections": [{
                    "widgets":
                        [{"textParagraph": {"text": "Выберите пользователей:"}},
                         {
                             "selectionInput": {
                                 "name": "contacts",
                                 "type": "MULTI_SELECT",
                                 "label": "Участники опроса",
                                 "multiSelectMaxSelectedItems": 20,
                                 "multiSelectMinQueryLength": 1,
                                 "platformDataSource": {
                                     "commonDataSource": "USER"
                                 }
                             }
                         },
                         {
                             "buttonList": {
                                 "buttons": [{
                                     "text": f"Отправить {text}",
                                     "onClick": {
                                         "action": {
                                             "function": "send_to_final_user",
                                             "parameters": [
                                                 {"key": "state", "value": state},
                                                 {"key": "update", "value": "True"},
                                                 {"key":"quiz","value":quiz_json}
                                             ]

                                         }
                                     }
                                 }]
                             }
                         }
                    ]
                }]
            }
        }]
    }


def send_message(message, user):
    try:
        dm_space = chat_service.spaces().findDirectMessage(
            name=user
        ).execute()

        response = chat_service.spaces().messages().create(
            parent=dm_space.get('name'), body=message
        ).execute()

        if "error" in response:
            return {
                    "text": f"Ошибка при отправке сообщения: {response['error']}"}

    except Exception as e:
        return {
                "text": f"Ошибка при выполнении запроса: {str(e)}"}

def counting_users(sender_name,quiz_id):
    doc_ref = db.collection("User_quizs").document(sender_name)
    quiz_ref = doc_ref.collection("Quizs").document(quiz_id)
    users_ref = quiz_ref.collection("Users").stream()
    users_dict={
        "possitive":[],
        "negative":[],
        "unanswered":[],
        "reasons_dict":{}
        }
    members=get_members()

    for user_doc in users_ref :
        doc= user_doc.to_dict()
        doc_id= user_doc.id
        doc_id = doc_id.replace('_','/').strip()
        if doc_id in members:
            display_name= members[doc_id]
            match doc.get('state'):
                case True :
                    users_dict['possitive'].append(display_name)
                case False :
                    users_dict['negative'].append(display_name)
                case None :
                    users_dict['unanswered'].append(display_name)
            if doc.get('reason') is not None:
                users_dict['reasons_dict'][display_name]= doc.get('reason')


        else:
            users_dict['unanswered'].append(f"Unknown User ({doc_id})")

    return users_dict

def format_users_dict(users,comments=None):
    if not users:
        return "—"
    result = []
    for user in users:
        comment = comments.get(user) if comments else None
        if comment:

            result.append(f"•<b> {user}</b> ( {comment} )")
        else:
            result.append(f"• <b>{user}</b> ")
    return "\n".join(result)

def card_about_users( users_dict, quiz_name,end_widgets=None,start_widgets=None):


    positive_users = format_users_dict(users_dict.get('possitive',{}))
    negative_users = format_users_dict(users_dict.get('negative',{}), users_dict.get('reasons_dict',{}))

    if end_widgets is None:
        end_widgets=[]
    if start_widgets is None:
        start_widgets =[]

    base_widgets =[
                        {"textParagraph": {
                            "text": f"*Пользователи подтвердившие документ*\n{positive_users}" if positive_users else "—"}},
                        {
                            "divider": {}
                        },
                        {"textParagraph": {
                            "text": f"*Пользователи отклонившие документ*\n{negative_users}" if negative_users else "—"}},
                        {
                            "divider": {}
                        },
                  ]
    start_widgets.extend(base_widgets)
    start_widgets.extend(end_widgets)

    card = {
        "text":"",
        "cardsV2": [{
            "cardId": "result_card",
            "card": {
                "header": {"title": f"РЕЗУЛЬТАТ ОПРОСА: {quiz_name}"},
                "sections": [{
                    "widgets": start_widgets
                }]
            }
        }]
    }


    return card

def update_message(name,body,update_mask):
    response = chat_service.spaces().messages().update(
        name=name,
        body=body,
        updateMask=update_mask
    ).execute()

def get_members():
    members = {}
    # запрос для поиска user_name

    request = chat_service.spaces().members().list(parent=SPACE_GROUP).execute()
    for member in request.get('memberships', []):
        name = member['member']['name']
        display_name = member['member'].get('displayName', 'Unknown')  # Имя пользователя
        members[name] = display_name
    return members


def send_to_gmail(user_gmail, users_dict, quiz):
    users = users_dict.get('possitive')

    html_template = """
    <html>
    <head>
        <style>
            body { font-family: Arial, sans-serif; }
            .container { padding: 20px; background-color: #f4f4f4; }
            .content { padding: 15px; background: white; border-radius: 5px; }
            h2 { color: #333; }
            a { color: #1a73e8; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="content">
                <h2>Результат опроса</h2>
                <p><strong>Пользователи, подтвердившие документ:</strong></p>
                {% for user in users %}
                    <p><b>• {{ user }}</b></p>
                {% endfor %}
                {% if url %}
                    <hr>
                    <p><strong>Ссылка на документ:</strong></p>
                    <p><a href="{{ url }}">{{ url }}</a></p>
                {% endif %}
            </div>
        </div>
    </body>
    </html>
    """

    url = None
    if quiz.url_link and not quiz.attachment:
        url = quiz.url_link.link

    template = Template(html_template)
    html_content = template.render(users=users, url=url)

    service_gmail = build("gmail", "v1", credentials=delegated_credentials)

    # Создание письма
    msg = MIMEMultipart()
    msg["to"] = user_gmail
    msg["subject"] = f"Ознакомьтесь с результатом опроса {quiz.quiz_name}"

    # Добавление HTML тела
    msg.attach(MIMEText(html_content, "html"))

    # Если прикреплён файл
    if quiz.attachment and not quiz.url_link:
        attach = quiz.attachment
        file = download_file(attach.file, attach.content)
        file_path = file["file"]
        encoded_filename = encode_rfc2231(attach.name, "utf-8")

        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename*={encoded_filename}")
            msg.attach(part)

    # Создание и отправка письма
    raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    message = {"raw": raw_message}
    service_gmail.users().messages().send(userId="me", body=message).execute()
