import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Menu, Paperclip, MoreVertical, Bot, X, BrainCircuit, Clock, ChevronDown, ChevronUp, Trash2 } from 'lucide-react';
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
  thoughts?: string[];
  duration?: number;
  timestamp: string;
  status?: 'sending' | 'sent' | 'error';
  attachment?: string;
};

const MODELS = [
  { id: 'glm-5.2', name: 'هوشمند - GLM 5.2 (فکر کردن)' },
  { id: 'llama-3.3-70b', name: 'سریع - Llama 3.3 70B' },
  { id: 'deepseek-r1', name: 'عمیق - DeepSeek R1' },
];

export default function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [attachment, setAttachment] = useState<{file: File, base64: string, preview?: string} | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isTyping, setIsTyping] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [selectedModel, setSelectedModel] = useState('glm-5.2');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Initialize
  useEffect(() => {
    // @ts-ignore
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
      tg.setHeaderColor('#ffffff');
      tg.setBackgroundColor('#f8fafc');
    }
    
    // Load history
    try {
      const saved = localStorage.getItem('chat_history');
      if (saved) {
        setMessages(JSON.parse(saved));
      } else {
        setMessages([
          {
            id: '1',
            role: 'assistant',
            content: 'سلام! من دستیار هوشمند شما هستم. چطور می‌توانم امروز به شما کمک کنم؟',
            timestamp: new Date(Date.now() - 60000).toISOString(),
            status: 'sent',
          }
        ]);
      }
    } catch (e) {
      // ignore
    }
  }, []);
  
  // Save history
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem('chat_history', JSON.stringify(messages));
    }
  }, [messages]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    // Max 10MB
    if (file.size > 10 * 1024 * 1024) {
        alert('حجم فایل نباید بیشتر از 10 مگابایت باشد.');
        return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      const base64String = (event.target?.result as string).split(',')[1];
      setAttachment({
        file,
        base64: base64String,
        preview: file.type.startsWith('image/') ? (event.target?.result as string) : undefined
      });
    };
    reader.readAsDataURL(file);
  };

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if ((!inputValue.trim() && !attachment) || isTyping) return;

    const currentInput = inputValue.trim();
    const newUserMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: currentInput,
      // temporary property to display image in chat
      ...(attachment?.preview ? { attachment: attachment.preview } : {}),
      timestamp: new Date().toISOString(),
      status: 'sending',
    };

    setMessages((prev) => [...prev, newUserMsg]);
    setInputValue('');
    setAttachment(null);
    setIsTyping(true);

    try {
      // Prepare history
      const history = messages.map(m => ({ role: m.role, content: m.content }));
      
      // @ts-ignore
      const chatId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || '';
      
            const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            message: currentInput, 
            history,
            model: selectedModel,
            chat_id: chatId,
            attachment: attachment ? {
                base64: attachment.base64,
                mime_type: attachment.file.type,
                filename: attachment.file.name
            } : undefined
        }),
      });

      if (!response.ok || !response.body) throw new Error('Network response was not ok');

      const aiMsgId = (Date.now() + 1).toString();
      setMessages((prev) => [
        ...prev.map((msg) => (msg.id === newUserMsg.id ? { ...msg, status: 'sent' } : msg)),
        {
          id: aiMsgId,
          role: 'assistant',
          content: '',
          thoughts: [],
          status: 'sending',
          timestamp: new Date().toISOString()
        }
      ]);

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        let currentEvent = '';
        let shouldBreak = false;
        
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            if (!dataStr) continue;
            try {
              const data = JSON.parse(dataStr);
              if (currentEvent === 'step') {
                 setMessages(prev => prev.map(m => {
                  if (m.id === aiMsgId) {
                    const thoughts = [...(m.thoughts || [])];
                    thoughts.push('');
                    return { ...m, thoughts };
                  }
                  return m;
                }));
              } else if (currentEvent === 'reasoning') {
                setMessages(prev => prev.map(m => {
                  if (m.id === aiMsgId) {
                    const thoughts = [...(m.thoughts || [])];
                    if (thoughts.length === 0) thoughts.push('');
                    thoughts[thoughts.length - 1] += data.chunk;
                    return { ...m, thoughts };
                  }
                  return m;
                }));
              } else if (currentEvent === 'content') {
                setMessages(prev => prev.map(m => {
                  if (m.id === aiMsgId) {
                    return { ...m, content: m.content + data.chunk };
                  }
                  return m;
                }));
              } else if (currentEvent === 'done') {
                setMessages(prev => prev.map(m => {
                  if (m.id === aiMsgId) {
                    return { 
                      ...m, 
                      content: data.reply, 
                      thoughts: data.thoughts, 
                      status: 'sent' 
                    };
                  }
                  return m;
                }));
                shouldBreak = true; break;
              } else if (currentEvent === 'error') {
                setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, status: 'error', content: m.content + '\n[خطا: ' + data.message + ']' } : m));
                shouldBreak = true; break;
              }
            } catch (e) {
              console.error("Parse error", e);
            }
          }
        }
        if (shouldBreak) break;
      }
    } catch (error) {
      console.error(error);
      setMessages((prev) =>
        prev.map((msg) => (msg.id === newUserMsg.id ? { ...msg, status: 'error' } : msg))
      );
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: '⚠️ خطایی در ارتباط با سرور رخ داد. لطفا دوباره تلاش کنید.',
        timestamp: new Date().toISOString(),
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
      
      {/* Settings Modal */}
      <AnimatePresence>
        {showSettings && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-slate-900/50 z-50 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4"
            onClick={() => setShowSettings(false)}
          >
            <motion.div 
              initial={{ y: "100%" }}
              animate={{ y: 0 }}
              exit={{ y: "100%" }}
              transition={{ type: "spring", bounce: 0, duration: 0.4 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-md bg-white rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden"
            >
              <div className="p-4 border-b border-slate-100 flex items-center justify-between">
                <h3 className="font-bold text-lg text-slate-800">تنظیمات ربات</h3>
                <button onClick={() => setShowSettings(false)} className="p-2 hover:bg-slate-100 rounded-full text-slate-500 transition-colors">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="p-6 flex flex-col gap-6">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">مدل هوش مصنوعی</label>
                  <select 
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                    className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-slate-700 outline-none"
                    dir="rtl"
                  >
                    {MODELS.map(m => (
                      <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                  </select>
                </div>
                
                <div>
                  <button 
                    onClick={() => {
                        if(window.confirm('آیا از حذف تاریخچه مطمئن هستید؟')) {
                            setMessages([]);
                            localStorage.removeItem('chat_history');
                            setShowSettings(false);
                        }
                    }}
                    className="w-full p-3 flex items-center justify-center gap-2 text-red-600 bg-red-50 hover:bg-red-100 rounded-xl transition-colors font-medium"
                  >
                    <Trash2 className="w-4 h-4" />
                    پاک کردن تاریخچه مکالمات
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

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
          <button className="p-2 hover:bg-slate-100 rounded-lg border border-slate-200 text-slate-600 transition-colors" onClick={() => setShowSettings(true)}>
            <Menu className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Chat Area */}
      <main className="flex-1 overflow-y-auto p-4 sm:p-8 flex flex-col gap-6 sm:gap-8">
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
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
                 <span className="text-xs text-slate-400 ms-2">در حال فکر کردن...</span>
               </div>
             </motion.div>
          )}
        </AnimatePresence>
        <div ref={messagesEndRef} className="h-4" />
      </main>

      {/* Input Area */}
      <footer className="p-4 sm:p-8 bg-gradient-to-t from-slate-50 via-slate-50 to-transparent">
                {attachment && (
            <div className="max-w-4xl mx-auto mb-2 bg-indigo-50 border border-indigo-100 rounded-xl p-3 flex items-center justify-between">
                <div className="flex items-center gap-3 overflow-hidden">
                    {attachment.preview ? (
                        <img src={attachment.preview} alt="preview" className="w-10 h-10 object-cover rounded-lg" />
                    ) : (
                        <div className="w-10 h-10 bg-indigo-100 text-indigo-500 rounded-lg flex items-center justify-center">
                            <Paperclip className="w-5 h-5" />
                        </div>
                    )}
                    <span className="text-sm font-medium text-slate-700 truncate">{attachment.file.name}</span>
                </div>
                <button type="button" onClick={() => setAttachment(null)} className="p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 rounded-lg">
                    <X className="w-4 h-4" />
                </button>
            </div>
        )}
        <form 
          onSubmit={handleSend}
          className="max-w-4xl mx-auto bg-white border border-slate-200 rounded-2xl shadow-xl p-2 flex items-end gap-2 focus-within:ring-2 focus-within:ring-indigo-500/20 transition-all"
        >
          <input 
            type="file" 
            ref={fileInputRef} 
            className="hidden" 
            onChange={handleFileChange}
          />
          <button 
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className={cn("p-3 transition-colors flex-shrink-0", attachment ? "text-indigo-600" : "text-slate-400 hover:text-indigo-600")}
          >
            <Paperclip className="w-5 h-5 sm:w-6 sm:h-6" />
          </button>
          
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="سوال یا دستور خود را بنویسید (مثلا: فردا ساعت 8 صبح یادآوری کن...)"
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
          قدرت گرفته از سیستم پیشرفته استریمینگ • نسخه پرمیوم ۱.۵
        </p>
      </footer>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Message }) {
  const [userToggled, setUserToggled] = useState(false);
  const [showThoughts, setShowThoughts] = useState(false);
  
  useEffect(() => {
    if (!userToggled) {
      if (msg.status === 'sending' && msg.thoughts && msg.thoughts.length > 0) {
        setShowThoughts(true);
      } else if (msg.status === 'sent' || msg.status === 'error') {
        setShowThoughts(false);
      }
    }
  }, [msg.status, msg.thoughts?.length, userToggled]);

  const date = new Date(msg.timestamp);
  
  return (
    <motion.div
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
      
      <div className="flex flex-col gap-1 min-w-0 w-full">
        <div
          className={cn(
            "p-4 sm:p-5 rounded-2xl shadow-sm text-sm sm:text-[15px] leading-relaxed text-pretty whitespace-pre-wrap",
            msg.role === 'user' 
              ? "bg-white border border-slate-200 rounded-tr-none text-slate-800" 
              : "bg-indigo-50/50 border border-indigo-100 rounded-tl-none text-slate-800"
          )}
        >
          {/* Thoughts Section */}
          {msg.thoughts && msg.thoughts.length > 0 && (
              <div className="mb-3">
                  <button 
                    onClick={() => {
                      setUserToggled(true);
                      setShowThoughts(!showThoughts);
                    }}
                    className="flex items-center gap-2 text-xs font-medium text-slate-500 bg-white/60 hover:bg-white p-2 rounded-lg transition-colors border border-slate-200/50 w-full"
                  >
                    <BrainCircuit className="w-4 h-4 text-indigo-500" />
                    <span>فرایند فکر کردن مدل ({msg.thoughts.length} مرحله)</span>
                    {showThoughts ? <ChevronUp className="w-3 h-3 ms-auto" /> : <ChevronDown className="w-3 h-3 ms-auto" />}
                  </button>
                  <AnimatePresence>
                      {showThoughts && (
                          <motion.div 
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              className="overflow-hidden"
                          >
                              <div className="mt-2 p-3 bg-slate-800 text-slate-300 rounded-xl text-xs sm:text-sm font-mono leading-relaxed border border-slate-700 max-h-60 overflow-y-auto whitespace-pre-wrap">
                                  {msg.thoughts.map((t, i) => (
                                      <div key={i} className="mb-2 last:mb-0 pb-2 last:pb-0 border-b border-slate-700/50 last:border-0">
                                          <span className="text-slate-500 me-2">[{i+1}]</span>
                                          {t}
                                      </div>
                                  ))}
                              </div>
                          </motion.div>
                      )}
                  </AnimatePresence>
              </div>
          )}
          
                    {msg.attachment && (
            <div className="mb-3 rounded-lg overflow-hidden border border-slate-200/50">
              <img src={msg.attachment} alt="attachment" className="w-full h-auto max-h-64 object-cover" />
            </div>
          )}
          <div dir="auto">{msg.content}</div>
        </div>
        <div 
          className={cn(
            "text-[10px] text-slate-400 flex items-center gap-1 mx-1 mt-1",
            msg.role === 'user' ? "justify-end" : "justify-start"
          )}
        >
          <Clock className="w-3 h-3 opacity-70" />
          {date.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })}
          {msg.duration && (
              <span className="ms-2 opacity-80 text-indigo-500 font-mono bg-indigo-50 px-1 rounded">
                  {msg.duration} ثانیه
              </span>
          )}
          {msg.role === 'user' && msg.status === 'sending' && (
            <span className="opacity-50"> • در حال ارسال...</span>
          )}
        </div>
      </div>
    </motion.div>
  );
}
