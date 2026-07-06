import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Menu, Paperclip, MoreVertical, Bot } from 'lucide-react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

// --- Utility for Tailwind ---
function cn(...inputs: (string | undefined | null | false)[]) {
  return twMerge(clsx(inputs));
}

// --- Types ---
type Message = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  status?: 'sending' | 'sent' | 'error';
};

// --- Mock Initial Data ---
const INITIAL_MESSAGES: Message[] = [
  {
    id: '1',
    role: 'assistant',
    content: 'سلام! من دستیار هوشمند شما هستم. چطور می‌توانم امروز به شما کمک کنم؟',
    timestamp: new Date(Date.now() - 60000),
    status: 'sent',
  },
];

export default function App() {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Initialize Telegram Web App
  useEffect(() => {
    // @ts-ignore
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      // Inform Telegram about background colors for seamless integration
      tg.setHeaderColor('#ffffff'); // Corresponds to bg-white header
      tg.setBackgroundColor('#f8fafc'); // Corresponds to slate-50
    }
  }, []);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!inputValue.trim() || isTyping) return;

    const currentInput = inputValue.trim();
    const newUserMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: currentInput,
      timestamp: new Date(),
      status: 'sending',
    };

    setMessages((prev) => [...prev, newUserMsg]);
    setInputValue('');
    setIsTyping(true);

    try {
      // Prepare history
      const history = messages.map(m => ({ role: m.role, content: m.content }));
      
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: currentInput, history }),
      });

      if (!response.ok) throw new Error('Network response was not ok');
      
      const data = await response.json();
      
      setMessages((prev) =>
        prev.map((msg) => (msg.id === newUserMsg.id ? { ...msg, status: 'sent' } : msg))
      );

      const newAiMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: data.reply || 'پاسخی دریافت نشد.',
        timestamp: new Date(),
        status: 'sent',
      };
      
      setMessages((prev) => [...prev, newAiMsg]);
    } catch (error) {
      console.error(error);
      setMessages((prev) =>
        prev.map((msg) => (msg.id === newUserMsg.id ? { ...msg, status: 'error' } : msg))
      );
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: '⚠️ خطایی در ارتباط با سرور رخ داد. لطفا دوباره تلاش کنید.',
        timestamp: new Date(),
        status: 'error',
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto bg-slate-50 text-slate-900 overflow-hidden relative font-sans shadow-2xl sm:border-x border-slate-200">
      
      {/* Header */}
      <header className="h-16 sm:h-20 bg-white/80 backdrop-blur-md border-b border-slate-200 flex items-center justify-between px-4 sm:px-8 z-10">
        <div className="flex items-center gap-4">
          <div className="flex flex-col">
            <h2 className="text-base sm:text-lg font-bold text-slate-800">هوش مصنوعی آریا</h2>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 bg-green-500 rounded-full"></span>
              <span className="text-xs text-slate-500 font-medium">متصل و آماده</span>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="p-2 hover:bg-slate-100 rounded-lg border border-slate-200 text-slate-600 transition-colors" onClick={() => { if(window.Telegram?.WebApp) { window.Telegram.WebApp.showAlert("امکانات پروفایل و تاریخچه به‌زودی اضافه می‌شود."); } else { alert("امکانات پروفایل و تاریخچه به‌زودی اضافه می‌شود."); } }}>
            <Menu className="w-5 h-5" />
          </button>
          <button className="p-2 hover:bg-slate-100 rounded-lg border border-slate-200 text-slate-600 transition-colors hidden sm:block">
            <MoreVertical className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Chat Area */}
      <main className="flex-1 overflow-y-auto p-4 sm:p-8 flex flex-col gap-6 sm:gap-8">
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.3, type: 'spring', bounce: 0.3 }}
              className={cn(
                "flex gap-3 sm:gap-4 max-w-3xl",
                msg.role === 'user' ? "flex-row-reverse ms-auto" : "me-auto"
              )}
            >
              {msg.role === 'assistant' ? (
                <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white shrink-0 shadow-lg shadow-indigo-200 font-bold text-sm sm:text-base">
                  A
                </div>
              ) : (
                <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-slate-200 shrink-0"></div>
              )}
              
              <div className="flex flex-col gap-1 min-w-0">
                <div
                  className={cn(
                    "p-4 sm:p-5 rounded-2xl shadow-sm text-sm sm:text-[15px] leading-relaxed text-pretty",
                    msg.role === 'user' 
                      ? "bg-white border border-slate-200 rounded-tr-none text-slate-800" 
                      : "bg-indigo-50/50 border border-indigo-100 rounded-tl-none text-slate-800"
                  )}
                >
                  {msg.content}
                </div>
                <div 
                  className={cn(
                    "text-[10px] text-slate-400 flex items-center gap-1 mx-1",
                    msg.role === 'user' ? "justify-end" : "justify-start"
                  )}
                >
                  {msg.timestamp.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })}
                  {msg.role === 'user' && msg.status === 'sending' && (
                    <span className="opacity-50"> • در حال ارسال...</span>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
          
          {/* Typing Indicator */}
          {isTyping && (
             <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9 }}
              className="flex gap-3 sm:gap-4 max-w-3xl me-auto opacity-70"
             >
               <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white shrink-0">
                  A
               </div>
               <div className="flex items-center gap-2 h-10 px-2">
                 <motion.span className="w-1.5 h-1.5 bg-indigo-400 rounded-full" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1, repeat: Infinity, delay: 0 }} />
                 <motion.span className="w-1.5 h-1.5 bg-indigo-400 rounded-full" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1, repeat: Infinity, delay: 0.2 }} />
                 <motion.span className="w-1.5 h-1.5 bg-indigo-400 rounded-full" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1, repeat: Infinity, delay: 0.4 }} />
                 <span className="text-xs text-slate-400 ms-2">در حال تایپ پاسخ...</span>
               </div>
             </motion.div>
          )}
        </AnimatePresence>
        <div ref={messagesEndRef} className="h-4" />
      </main>

      {/* Input Area */}
      <footer className="p-4 sm:p-8 bg-gradient-to-t from-slate-50 via-slate-50 to-transparent">
        <form 
          onSubmit={handleSend}
          className="max-w-4xl mx-auto bg-white border border-slate-200 rounded-2xl shadow-xl p-2 flex items-end gap-2 focus-within:ring-2 focus-within:ring-indigo-500/20 transition-all"
        >
          <button 
            type="button"
            className="p-3 text-slate-400 hover:text-indigo-600 transition-colors flex-shrink-0"
          >
            <Paperclip className="w-5 h-5 sm:w-6 sm:h-6" />
          </button>
          
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="سوال خود را اینجا بپرسید..."
            className="flex-1 border-0 focus:ring-0 py-3 sm:py-3.5 px-2 text-sm sm:text-base resize-none bg-transparent max-h-32 min-h-[48px] sm:min-h-[52px] overflow-auto outline-none text-slate-800 placeholder:text-slate-400"
            rows={1}
            dir="auto"
          />
          
          <button
            type="submit"
            disabled={!inputValue.trim()}
            className={cn(
              "p-3 rounded-xl flex items-center justify-center transition-all flex-shrink-0 shadow-lg",
              inputValue.trim() 
                ? "bg-indigo-600 text-white hover:bg-indigo-700 shadow-indigo-200 active:scale-95" 
                : "bg-slate-100 text-slate-400 shadow-transparent cursor-not-allowed"
            )}
          >
            <Send className="w-5 h-5 sm:w-6 sm:h-6 -ms-0.5" />
          </button>
        </form>
        <p className="text-center text-[10px] sm:text-xs text-slate-400 mt-4 font-medium tracking-wide">
          قدرت گرفته از سیستم پیشرفته استریمینگ • نسخه پرمیوم ۱.۴
        </p>
      </footer>
    </div>
  );
}
