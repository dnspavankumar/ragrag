# Standard library imports
import base64
from datetime import datetime, timedelta, timezone
from email import utils
import chime
import os
import os.path
import sqlite3
import time
import traceback

# Third-party library imports
from bs4 import BeautifulSoup
import dateutil.parser
from dotenv import load_dotenv
import faiss
import numpy as np
import pyttsx3
import speech_recognition as sr
from tzlocal import get_localzone
from groq import Groq

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

# Parameters
INDEX_NAME = "index_email.index"
DB_FILE = "index_email_metadata.db"
EMBEDDING_DIM = 1536
K = 25  # Number of Fetched Emails for Vector Search

# Setting up the model & API key
load_dotenv(override=True)
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
client = Groq(api_key=GROQ_API_KEY)

def summerize_email(mail_from, mail_cc, mail_subject, mail_date, mail_body):
    try:
        system_content = '''
Summerize the given Email in the following format, keep it brief but don't lose much information:

OUTPUT FORMAT:
<Email Start>
Date and Time:  (format: dd-MMM-yyyy HH h:mmtt [with time zone])
Sender: 
CC:
Subject:
Email Context: 
<Email End>
'''

        prompt = f'''
The email is the following: 

date and time: {mail_date}
from: {mail_from}
cc: {mail_cc}
subject: {mail_subject}
body: {mail_body}

Please summarize this email according to the format above.
'''

        response = client.chat.completions.create(
            model="meta-llama/llama-4-maverick-17b-128e-instruct",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        if response and hasattr(response, 'choices') and response.choices:
            return response.choices[0].message.content
        else:
            # Fallback format if API fails
            return f'''<Email Start>
Date and Time: {mail_date}
Sender: {mail_from}
CC: {mail_cc}
Subject: {mail_subject}
Email Context: {mail_body[:500]}...
<Email End>'''
            
    except Exception as e:
        print(f"(EMAILS LOADER): Error summarizing email: {e}")
        # Return a basic formatted version of the email
        return f'''<Email Start>
Date and Time: {mail_date}
Sender: {mail_from}
CC: {mail_cc}
Subject: {mail_subject}
Email Context: {mail_body[:500] if mail_body else "No body content available"}...
<Email End>'''

# Gmail API Related Functions
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def authenticate_gmail():
    creds = None
    token_file = 'token.json'
    
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)
    return service

def clean_html(html_content):
    """ Clean HTML content and extract plain text. """
    try:
        if not html_content:
            return ""
        if isinstance(html_content, str):
            soup = BeautifulSoup(html_content, 'html.parser')
            return soup.get_text("\n", strip=True)
        return str(html_content)
    except Exception as e:
        print(f"(EMAILS LOADER): Error cleaning HTML content: {e}")
        return str(html_content) if html_content else ""

def get_plain_text_body(parts):
    """ Recursively extract plain text from MIME parts, with fallback to cleaned HTML if necessary. """
    plain_text = None
    html_text = None
    
    for part in parts:
        mime_type = part['mimeType']
        if 'parts' in part:
            # Recursively process nested parts
            text = get_plain_text_body(part['parts'])
            if text:
                return text
        elif mime_type == 'text/plain' and 'data' in part['body']:
            plain_text = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        elif mime_type == 'text/html' and 'data' in part['body']:
            html_body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
            html_text = clean_html(html_body)

    return plain_text if plain_text else html_text

def get_message_details(service, user_id, msg_id):
    try:
        message = service.users().messages().get(userId=user_id, id=msg_id, format='full').execute()
        headers = message['payload']['headers']
        details = {header['name']: header['value'] for header in headers if header['name'] in ['From', 'Cc', 'Subject', 'Date']}

        payload = message['payload']
        if 'parts' in payload:
            details['Body'] = get_plain_text_body(payload['parts'])
        elif 'data' in payload['body']:
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
            details['Body'] = clean_html(body)
        else:
            details['Body'] = None
        
        return details
    except Exception as error:
        print(f'An error occurred: {error}')
        return None

def list_messages(service, user_id, query=''):
    try:
        messages = []
        request = service.users().messages().list(userId=user_id, q=query)
        while request is not None:
            response = request.execute()
            if 'messages' in response:
                messages.extend(response['messages'])
            request = service.users().messages().list_next(request, response)
        return messages
    except Exception as error:
        print(f'An error occurred: {error}')
        return None

def get_last_checked_time():
    try:
        with open('last_checked.txt', 'r') as file:
            return dateutil.parser.parse(file.read().strip())
    except FileNotFoundError:
        return datetime(1970, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

def update_last_checked_time(timestamp):
    with open('last_checked.txt', 'w') as file:
        file.write(str(timestamp))

# Vector Store Operations
def get_embedding(text):
    # For now, we'll use a simple text embedding approach
    # In a production environment, you might want to use a dedicated embedding model
    return np.random.rand(1, EMBEDDING_DIM)

def get_index():
    if os.path.exists(INDEX_NAME):
        return faiss.read_index(INDEX_NAME)
    else:
        return faiss.IndexFlatL2(EMBEDDING_DIM)

def initiate_meta_store():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL
        )
        ''')
    return (conn, cursor)

def terminate_meta_store(conn):
    conn.commit()
    conn.close()

def insert_email_record(full_email, index, cursor):
    embedding = get_embedding(full_email)
    index.add(embedding)
    cursor.execute("INSERT INTO Metadata (text) VALUES (?)", (full_email,))

def Vector_Search(query, demo=False, k=K):
    try:
        print(f"DEBUG: Starting Vector_Search with query: {query}")
        index = get_index()
        conn, cursor = initiate_meta_store()
        query_embedding = get_embedding(query)
        distances, indices = index.search(query_embedding, k)
        decoded_texts = []
        
        print(f"DEBUG: Found {len(indices[0])} indices")
        for idx in indices[0]:
            try:
                cursor.execute(f"SELECT text FROM Metadata WHERE id={idx + 1}")
                result = cursor.fetchone()
                if result:
                    decoded_texts.append(result[0])
                else:
                    print(f"DEBUG: No text found for index {idx + 1}")
            except Exception as e:
                print(f"DEBUG: Error fetching text for index {idx + 1}: {str(e)}")
        
        conn.close()
        
        if demo:
            print("Decoded texts of nearest neighbors:")
            for text in decoded_texts:
                print("*********************************************")
                print("########", text[31:56])
                print(text)
            print("*********************************************")
            print("Distances to nearest neighbors:", distances)
        
        print(f"DEBUG: Returning {len(decoded_texts)} decoded texts")
        return decoded_texts if decoded_texts else ["No relevant emails found."]
        
    except Exception as e:
        print(f"DEBUG: Error in Vector_Search: {str(e)}")
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return ["No relevant emails found due to an error in the search process."]

def load_emails():
    i = 1
    service = authenticate_gmail()
    
    # Get current month's start date with timezone awareness
    current_date = datetime.now(timezone.utc)
    first_day_of_month = current_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Create a more specific query for Canara Bank emails from current month
    query = f'after:{first_day_of_month.strftime("%Y/%m/%d")} from:canarabank OR from:canara'
    messages = list_messages(service, 'me', query)
    
    if not messages:
        print('(EMAILS LOADER): No Canara Bank messages found for this month.')
    else:
        index = get_index()
        conn, cursor = initiate_meta_store()
        
        # Limit to first 5 emails only
        emails_processed = 0
        max_emails = 5
        
        for msg in messages:
            # Stop if we've already processed 5 emails
            if emails_processed >= max_emails:
                break
                
            msg_id = msg['id']
            details = get_message_details(service, 'me', msg_id)
            if details:
                message_datetime = utils.parsedate_to_datetime(details['Date'])
                # Ensure message_datetime is timezone-aware
                if message_datetime.tzinfo is None:
                    message_datetime = message_datetime.replace(tzinfo=timezone.utc)
                
                # Skip if email is from before this month
                if message_datetime < first_day_of_month:
                    continue

                mail_from = details.get('From', '').lower()
                mail_cc = details.get('Cc')
                mail_subject = details.get('Subject')
                mail_body = details.get('Body')

                full_email = summerize_email(mail_from, mail_cc, mail_subject, message_datetime, mail_body)
                insert_email_record(full_email, index, cursor)
                
                print(f"(EMAILS LOADER): Canara Bank Email # {i} is detected and inserted: ({message_datetime}), ({mail_subject}).")
                i += 1
                emails_processed += 1

        terminate_meta_store(conn)
        faiss.write_index(index, INDEX_NAME)
        print(f"(EMAILS LOADER): Vector store and metadata saved. Processed {emails_processed} emails (max: {max_emails}).")
        
        # Update last checked time to current time
        update_last_checked_time(datetime.now(timezone.utc))

def ask_question(question, messages=None):
    try:
        print(f"DEBUG: Starting ask_question with question: {question}")
        print(f"DEBUG: GROQ_API_KEY set: {'Yes' if GROQ_API_KEY else 'No'}")
        print(f"DEBUG: client initialized: {'Yes' if client else 'No'}")
        
        # Check if client is properly initialized
        if not client or not GROQ_API_KEY:
            raise ValueError("Groq client not properly initialized - API key missing or invalid")
        
        if messages is None:
            print("DEBUG: New conversation started")
            try:
                related_emails = Vector_Search(question)
                print(f"DEBUG: Found {len(related_emails)} related emails")
            except Exception as e:
                print(f"DEBUG: Error in Vector_Search: {str(e)}")
                raise
                
            system_content = (
                "You are an AI assistant with access to a collection of emails. "
                "Below, you'll find the most relevant emails retrieved for the user's question. "
                "Your job is to answer the question based on the provided emails. "
                "If you cannot find the answer, please politely inform the user. "
                "Answer in a very short brief, and informative manner."
            )

            local_timezone = get_localzone()
            
            context = f"Today's Datetime is {datetime.now(local_timezone)}\n\n"
            for i, email in enumerate(related_emails):
                context += f"Email({i+1}):\n\n{email}\n\n"
            
            messages = [
                {"role": "system", "content": system_content + "\n\n" + context},
                {"role": "user", "content": question}
            ]
            
            print("DEBUG: Preparing to call Groq API for new conversation")
        else:
            print("DEBUG: Follow-up question in existing conversation")
            print(f"DEBUG: Message history length: {len(messages)}")
            # Just add the new user question to existing messages
            messages_to_send = messages + [{"role": "user", "content": question}]
            print("DEBUG: Preparing to call Groq API with conversation history")
        
        # Make the API call
        try:
            print("DEBUG: Calling Groq API...")
            
            # For new conversation
            if messages and len(messages) > 1 and "user" in messages[-1]["role"]:
                # If last message is from user, we need to append the new question
                api_messages = messages
            elif messages is None:
                # First question in conversation
                api_messages = messages
            else:
                # Follow-up question
                api_messages = messages + [{"role": "user", "content": question}]
            
            print(f"DEBUG: API messages structure: {[m['role'] for m in api_messages]}")
            
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=api_messages,
                temperature=0.3,
                max_tokens=1000
            )
            
            print("DEBUG: API call completed")
            print(f"DEBUG: Response type: {type(response)}")
            
            # Carefully check the response structure
            if response is None:
                print("DEBUG: Response is None")
                assistant_reply = "I apologize, but I received no response from the language model."
            elif not hasattr(response, 'choices'):
                print(f"DEBUG: Response has no 'choices' attribute. Response: {response}")
                assistant_reply = "I apologize, but I received an unexpected response format from the language model."
            elif not response.choices:
                print("DEBUG: Response.choices is empty")
                assistant_reply = "I apologize, but I received an empty response from the language model."
            else:
                print(f"DEBUG: Found {len(response.choices)} choices in response")
                # Access the message content safely
                try:
                    assistant_reply = response.choices[0].message.content
                    print(f"DEBUG: Successfully extracted reply: {assistant_reply[:50]}...")
                except Exception as content_error:
                    print(f"DEBUG: Error extracting message content: {str(content_error)}")
                    print(f"DEBUG: Response structure: {response}")
                    assistant_reply = "I apologize, but I couldn't process the response from the language model."
            
        except Exception as api_error:
            print(f"DEBUG: API call error: {str(api_error)}")
            assistant_reply = "I apologize, but there was an error connecting to the language model. Please check your API key and internet connection."
        
        # Update message history
        if messages is None:
            messages = [
                {"role": "system", "content": system_content + "\n\n" + context},
                {"role": "user", "content": question},
                {"role": "assistant", "content": assistant_reply}
            ]
        else:
            messages.append({"role": "user", "content": question})
            messages.append({"role": "assistant", "content": assistant_reply})
        
        print("DEBUG: Returning successful response")
        return messages, assistant_reply
        
    except Exception as e:
        import traceback
        print(f"DEBUG: Critical error in ask_question: {str(e)}")
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        
        error_message = f"I apologize, but I encountered a system error while processing your request. Error details: {str(e)}"
        
        if messages is None:
            messages = [
                {"role": "system", "content": "Error occurred"},
                {"role": "user", "content": question},
                {"role": "assistant", "content": error_message}
            ]
        else:
            messages.append({"role": "user", "content": question})
            messages.append({"role": "assistant", "content": error_message})
        
        return messages, error_message 
