import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import speech_recognition as sr
import pyttsx3
from RAG_Gmail import load_emails, ask_question
import time

print("Starting application...")  # Debug print

class AnimatedButton(tk.Canvas):
    def __init__(self, parent, text, command, width=120, height=35, **kwargs):
        super().__init__(parent, width=width, height=height, highlightthickness=0, **kwargs)
        self.command = command
        self.text = text
        self.width = width
        self.height = height
        
        # Colors
        self.bg_normal = "#2d2d30"
        self.bg_hover = "#404040"
        self.bg_active = "#505050"
        self.text_color = "#ffffff"
        self.border_color = "#404040"
        
        self.configure(bg=self.bg_normal)
        self.create_button()
        
        # Bind events
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)
        self.bind("<ButtonRelease-1>", self.on_release)
    
    def create_button(self):
        self.delete("all")
        # Draw rounded rectangle background
        self.create_rectangle(1, 1, self.width-1, self.height-1, 
                            fill=self.bg_normal, outline=self.border_color, width=1)
        # Draw text
        self.create_text(self.width//2, self.height//2, text=self.text, 
                        fill=self.text_color, font=("JetBrains Mono", 10, "bold"))
    
    def on_enter(self, event):
        self.configure(bg=self.bg_hover)
        self.delete("all")
        self.create_rectangle(1, 1, self.width-1, self.height-1, 
                            fill=self.bg_hover, outline="#606060", width=1)
        self.create_text(self.width//2, self.height//2, text=self.text, 
                        fill=self.text_color, font=("JetBrains Mono", 10, "bold"))
    
    def on_leave(self, event):
        self.configure(bg=self.bg_normal)
        self.create_button()
    
    def on_click(self, event):
        self.configure(bg=self.bg_active)
        self.delete("all")
        self.create_rectangle(1, 1, self.width-1, self.height-1, 
                            fill=self.bg_active, outline="#707070", width=1)
        self.create_text(self.width//2, self.height//2, text=self.text, 
                        fill=self.text_color, font=("JetBrains Mono", 10, "bold"))
    
    def on_release(self, event):
        if self.command:
            self.command()
        self.on_enter(event)

class VoiceThread(threading.Thread):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.daemon = True

    def run(self):
        recognizer = sr.Recognizer()
        try:
            with sr.Microphone() as source:
                audio = recognizer.listen(source)
                query = recognizer.recognize_google(audio)
                self.callback(query)
        except sr.UnknownValueError:
            messagebox.showerror("Error", "Could not understand audio")
        except sr.RequestError:
            messagebox.showerror("Error", "Could not request results; check your internet connection")
        except Exception as e:
            messagebox.showerror("Error", f"Error: {str(e)}")



class MessageBubble(tk.Frame):
    def __init__(self, parent, text, is_user=True, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(bg="#1e1e1e")
        
        # Create container for proper alignment
        container = tk.Frame(self, bg="#1e1e1e")
        container.pack(fill='x', pady=5)
        
        # Message content frame
        if is_user:
            # User message - right aligned, blue theme
            msg_frame = tk.Frame(container, bg="#2d5aa0", padx=15, pady=10)
            msg_frame.pack(side='right', anchor='e', padx=(100, 10))
            text_color = "#ffffff"
        else:
            # Assistant message - left aligned, dark theme  
            msg_frame = tk.Frame(container, bg="#2d2d30", padx=15, pady=10)
            msg_frame.pack(side='left', anchor='w', padx=(10, 100))
            text_color = "#e0e0e0"
        
        # Message text
        msg_label = tk.Label(msg_frame, text=text, bg=msg_frame['bg'], 
                           fg=text_color, font=("JetBrains Mono", 12, "normal"), 
                           wraplength=400, justify='left')
        msg_label.pack()

class GmailAssistantUI:
    def __init__(self, root):
        print("Initializing GmailAssistantUI...")  # Debug print
        self.root = root
        self.root.title("Gmail Assistant")
        self.root.geometry("1000x700")
        self.root.configure(bg="#1e1e1e")
        
        # Initialize variables
        self.messages = None
        self.new_conversation = True
        self.engine = pyttsx3.init()
        self.is_listening = False
        
        # Configure style
        self.setup_styles()
        
        # Create header
        self.create_header()
        
        # Create main layout
        self.create_main_layout()
        
        # Create input area
        self.create_input_area()
        
        # Load initial emails
        self.load_initial_emails()
        
        print("GmailAssistantUI initialized successfully")  # Debug print
        
        # Bind Enter key to send message (Ctrl+Enter for newline)
        self.input_field.bind("<Return>", self.handle_enter_key)
        self.input_field.bind("<Control-Return>", lambda e: self.input_field.insert(tk.INSERT, '\n'))
    
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure dark theme colors
        style.configure("Dark.TFrame", background="#1e1e1e")
        style.configure("Header.TFrame", background="#2d2d30")
        style.configure("Chat.TFrame", background="#1e1e1e")
        
        # Configure fonts with JetBrains Mono
        self.title_font = ("JetBrains Mono", 18, "bold")
        self.subtitle_font = ("JetBrains Mono", 11, "bold")
        self.chat_font = ("JetBrains Mono", 12, "normal")
        self.input_font = ("JetBrains Mono", 12, "normal")
    
    def create_header(self):
        # Header frame
        header_frame = tk.Frame(self.root, bg="#2d2d30", height=60)
        header_frame.pack(fill='x', side='top')
        header_frame.pack_propagate(False)
        
        # Header content
        header_content = tk.Frame(header_frame, bg="#2d2d30")
        header_content.pack(expand=True, fill='both')
        
        # Title
        title_label = tk.Label(header_content, text="Gmail Assistant", 
                              bg="#2d2d30", fg="#ffffff", font=self.title_font)
        title_label.pack(side='left', padx=20, pady=15)
        
        # Status indicator
        self.status_label = tk.Label(header_content, text="● Ready", 
                                   bg="#2d2d30", fg="#4ade80", font=self.subtitle_font)
        self.status_label.pack(side='left', padx=(0, 20), pady=15)
        
        # New chat button in header
        new_chat_btn = AnimatedButton(header_content, "New Chat", self.start_new_chat, 
                                    width=80, height=30, bg="#2d2d30")
        new_chat_btn.pack(side='right', padx=20, pady=15)
    
    def create_main_layout(self):
        # Main container
        main_container = tk.Frame(self.root, bg="#1e1e1e")
        main_container.pack(expand=True, fill='both', padx=20, pady=(0, 20))
        
        # Chat area
        chat_container = tk.Frame(main_container, bg="#1e1e1e")
        chat_container.pack(expand=True, fill='both', pady=(0, 20))
        
        # Custom chat display using Canvas for smooth scrolling (no scrollbar)
        self.chat_canvas = tk.Canvas(chat_container, bg="#1e1e1e", highlightthickness=0)
        self.chat_frame = tk.Frame(self.chat_canvas, bg="#1e1e1e")
        
        # Pack canvas without scrollbar
        self.chat_canvas.pack(fill="both", expand=True)
        
        # Create window in canvas
        self.canvas_window = self.chat_canvas.create_window((0, 0), window=self.chat_frame, anchor="nw")
        
        # Bind events for scrolling
        self.chat_frame.bind('<Configure>', self.on_frame_configure)
        self.chat_canvas.bind('<Configure>', self.on_canvas_configure)
        self.chat_canvas.bind_all("<MouseWheel>", self.on_mousewheel)
    
    def create_input_area(self):
        # Input container
        input_container = tk.Frame(self.root, bg="#1e1e1e", height=120)
        input_container.pack(fill='x', side='bottom', padx=20, pady=(0, 20))
        input_container.pack_propagate(False)
        
        # Input frame with border
        input_frame = tk.Frame(input_container, bg="#2d2d30", relief='solid', bd=1)
        input_frame.pack(fill='both', expand=True, ipady=2)
        
        # Input field
        self.input_field = tk.Text(input_frame, wrap=tk.WORD, height=3, 
                                 bg="#2d2d30", fg="#ffffff", font=self.input_font,
                                 insertbackground="#ffffff", relief='flat', bd=10)
        self.input_field.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Input field placeholder
        self.input_placeholder = "Type your message... (Press Enter to send, Ctrl+Enter for new line)"
        self.show_placeholder()
        self.input_field.bind('<FocusIn>', self.hide_placeholder)
        self.input_field.bind('<FocusOut>', self.show_placeholder)
        
        # Button container
        button_container = tk.Frame(input_container, bg="#1e1e1e")
        button_container.pack(fill='x', pady=(10, 0))
        
        # Buttons with modern styling
        self.send_button = AnimatedButton(button_container, "Send Message", self.send_message, 
                                        width=120, height=35, bg="#1e1e1e")
        self.send_button.pack(side='right', padx=(10, 0))
        
        self.voice_button = AnimatedButton(button_container, "🎤 Voice Input", self.start_voice_input, 
                                         width=120, height=35, bg="#1e1e1e")
        self.voice_button.pack(side='right')
    
    def show_placeholder(self, event=None):
        if not self.input_field.get("1.0", tk.END).strip():
            self.input_field.delete("1.0", tk.END)
            self.input_field.insert("1.0", self.input_placeholder)
            self.input_field.configure(fg="#808080")
    
    def hide_placeholder(self, event=None):
        if self.input_field.get("1.0", tk.END).strip() == self.input_placeholder:
            self.input_field.delete("1.0", tk.END)
            self.input_field.configure(fg="#ffffff")
    
    def handle_enter_key(self, event):
        if event.state & 4:  # Ctrl key is pressed
            return 'break'  # Let the default behavior happen (new line)
        else:
            self.send_message()
            return 'break'  # Prevent default behavior
    
    def on_frame_configure(self, event):
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
    
    def on_canvas_configure(self, event):
        canvas_width = event.width
        self.chat_canvas.itemconfig(self.canvas_window, width=canvas_width)
    
    def on_mousewheel(self, event):
        # Get current scroll position
        top, bottom = self.chat_canvas.yview()
        
        # Calculate scroll direction
        scroll_direction = int(-1*(event.delta/120))
        
        # Prevent scrolling above the top (top should not go below 0)
        if scroll_direction < 0 and top <= 0:
            return
        
        # Prevent scrolling below the bottom (bottom should not go above 1)
        if scroll_direction > 0 and bottom >= 1:
            return
            
        # Apply the scroll
        self.chat_canvas.yview_scroll(scroll_direction, "units")
    
    def add_message_bubble(self, text, is_user=True):
        bubble = MessageBubble(self.chat_frame, text, is_user)
        bubble.pack(fill='x', padx=10, pady=2)
        
        # Auto scroll to bottom
        self.root.after(10, lambda: self.chat_canvas.yview_moveto(1.0))
    
    def update_status(self, status, color="#4ade80"):
        self.status_label.configure(text=f"● {status}", fg=color)
        self.root.update()
    
    def load_initial_emails(self):
        try:
            print("Loading initial emails...")  # Debug print
            self.update_status("Loading emails...", "#fbbf24")
            load_emails()
            self.add_message_bubble("Emails loaded successfully! You can start asking questions about your Gmail.", False)
            self.update_status("Ready")
            print("Emails loaded successfully")  # Debug print
        except Exception as e:
            print(f"Error loading emails: {str(e)}")  # Debug print
            self.add_message_bubble(f"Failed to load emails: {str(e)}", False)
            self.update_status("Error loading emails", "#ef4444")
    
    def send_message(self):
        query = self.input_field.get("1.0", tk.END).strip()
        if not query or query == self.input_placeholder:
            return
        
        # Hide placeholder and clear input
        self.input_field.configure(fg="#ffffff")
        self.add_message_bubble(query, True)
        self.input_field.delete("1.0", tk.END)
        self.show_placeholder()
        
        # Update status
        self.update_status("Thinking...", "#fbbf24")
        
        # Process query in thread to avoid blocking UI
        threading.Thread(target=self.process_query, args=(query,), daemon=True).start()
    
    def process_query(self, query):
        try:
            if self.new_conversation:
                self.messages, response = ask_question(query)
                self.new_conversation = False
            else:
                self.messages, response = ask_question(query, messages=self.messages)
            
            # Update UI in main thread
            self.root.after(0, lambda: self.add_message_bubble(response, False))
            self.root.after(0, lambda: self.update_status("Ready"))
            
            # Use a thread for text-to-speech to avoid blocking
            threading.Thread(target=self.speak_text, args=(response,), daemon=True).start()
            
        except Exception as e:
            print(f"Error processing query: {str(e)}")  # Debug print
            self.root.after(0, lambda: self.add_message_bubble(f"Error: {str(e)}", False))
            self.root.after(0, lambda: self.update_status("Error", "#ef4444"))
    
    def speak_text(self, text):
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except:
            pass  # Ignore TTS errors
    
    def start_voice_input(self):
        if self.is_listening:
            return
            
        self.is_listening = True
        self.voice_button.text = "Listening..."
        self.voice_button.create_button()
        self.update_status("Listening...", "#fbbf24")
        
        def voice_callback(query):
            self.is_listening = False
            self.voice_button.text = "🎤 Voice Input"
            self.voice_button.create_button()
            self.update_status("Ready")
            
            if query:
                self.input_field.configure(fg="#ffffff")
                self.input_field.delete("1.0", tk.END)
                self.input_field.insert("1.0", query)
                self.send_message()
        
        VoiceThread(voice_callback).start()
    
    def start_new_chat(self):
        self.new_conversation = True
        self.messages = None
        
        # Clear chat display
        for widget in self.chat_frame.winfo_children():
            widget.destroy()
        
        # Add welcome message
        self.add_message_bubble("New conversation started! How can I help you with your emails?", False)
        self.update_status("Ready")

def main():
    print("Starting main function...")  # Debug print
    root = tk.Tk()
    
    # Set window icon and properties
    # root.wm_attributes('-type', 'dialog')  # Not supported on Windows
    
    print("Tk root created")  # Debug print
    app = GmailAssistantUI(root)
    print("Window created")  # Debug print
    
    # Center window on screen
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
    root.geometry(f"+{x}+{y}")
    
    root.mainloop()
    print("Window shown")  # Debug print

if __name__ == "__main__":
    print("Script started")  # Debug print
    main()