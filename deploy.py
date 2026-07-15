#!/usr/bin/env python3
"""
سكريبت النشر المحسن والمؤمن - Enhanced & Secure Deploy Script
يدعم النشر للموقع العربي والإنجليزي مع الحماية من حذف البيانات والتعامل مع الخوادم بدون صلاحيات Shell
"""

import os
import sys
import json
import hashlib
import fnmatch
import time
import argparse
from pathlib import Path

# Reconfigure stdout/stderr to use UTF-8 on Windows
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False


def mkdir_p(sftp, remote_directory):
    """إنشاء المجلدات البعيدة بشكل متكرر باستخدام SFTP فقط."""
    if remote_directory == "/" or remote_directory == "":
        return
    try:
        sftp.stat(remote_directory)
    except IOError:
        parent = os.path.dirname(remote_directory.rstrip('/'))
        mkdir_p(sftp, parent)
        print(f"Creating remote directory: {remote_directory}")
        sftp.mkdir(remote_directory)


def sftp_touch(sftp, filepath):
    """تحديث وقت التعديل أو إنشاء ملف فارغ باستخدام SFTP فقط (مفيد لعمل Restart للتطبيق)."""
    parent = os.path.dirname(filepath.rstrip('/'))
    mkdir_p(sftp, parent)
    try:
        with sftp.file(filepath, 'a'):
            pass
        now = time.time()
        sftp.utime(filepath, (now, now))
        print(f"  ✅ تم عمل ريستارت للتطبيق عبر لمس: {Path(filepath).name}")
    except Exception as e:
        print(f"  ⚠️  تحذير: لم نتمكن من لمس {filepath} بالـ SFTP: {e}")


class DeploymentManager:
    def __init__(self, site):
        self.site = site
        self.project_root = Path.cwd()
        
        # تحميل الإعدادات من deploy_config.json
        self.load_site_settings()
        
        # ملف الـ hashes منفصل لكل موقع لمنع التداخل
        self.hash_file = self.project_root / f".deploy_hashes_{self.site}.json"
        
        self.ignored_patterns = self.load_gitignore_patterns()
        self.uploaded_files = []
        
        print("🚀 سكريبت النشر المحسن والمؤمن")
        print("=" * 60)
        print(f"📁 المشروع:       {self.project_root.name}")
        print(f"🌐 الموقع المحدد:  {self.site.upper()}")
        print(f"🖥️  الخادم:        {self.server_ip}:{self.ssh_port}")
        print(f"📁 المجلد البعيد:   {self.remote_path}")
        print("=" * 60)

    def load_site_settings(self):
        """تحميل إعدادات الموقع المحدد من deploy_config.json"""
        config_path = self.project_root / "deploy_config.json"
        if not config_path.exists():
            print(f"❌ خطأ: لم يتم العثور على ملف الإعدادات: {config_path}")
            sys.exit(1)
            
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"❌ خطأ في قراءة ملف الإعدادات: {e}")
            sys.exit(1)
            
        site_config = config.get(self.site)
        if not site_config:
            print(f"❌ خطأ: إعدادات الموقع '{self.site}' غير موجودة في deploy_config.json")
            sys.exit(1)
            
        self.server_ip = site_config.get("host")
        self.ssh_port = site_config.get("port", 22)
        self.username = site_config.get("username")
        self.ssh_password = site_config.get("password")
        self.private_key = site_config.get("key_path")
        self.ssh_key_passphrase = site_config.get("passphrase")
        self.remote_path = site_config.get("remote_root")
        
        # افتراضية بايثون والـ DB
        self.python_version = "3.11"
        self.db_name = ""
        self.db_user = ""
        self.db_password = ""

    def load_gitignore_patterns(self):
        """تحميل قائمة الاستثناءات من .gitignore"""
        patterns = []
        gitignore_path = self.project_root / ".gitignore"
        
        if gitignore_path.exists():
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        patterns.append(line)
        
        # إضافة أنماط أساسية
        patterns.extend(['__pycache__', '*.pyc', '*.log', 'deploy_logs'])
        return patterns

    def is_ignored(self, file_path):
        """فحص ما إذا كان الملف مستثنى (مع حماية حاسمة لقواعد البيانات والملفات المرفوعة)"""
        relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
        
        # استثناءات نظام إجبارية لحماية وتأمين البيانات
        system_excludes = [
            'db.sqlite3',
            'media',
            'staticfiles',
            'id_rsa',
            'id_rsa_en',
            'deploy.py',
            'deploy_config.json',
            'deploy-Reference.py',
            'project.zip'
        ]
        
        for term in system_excludes:
            if relative_path == term or relative_path.startswith(term + '/'):
                return True
                
        # استثناء للملفات المهمة جداً
        important_files = [
            '.htaccess',
            '.env.production',
            'passenger_wsgi.py'
        ]
        
        if relative_path in important_files:
            return False
        
        # تجاهل مجلد deploy_logs
        if relative_path.startswith('deploy_logs/') or relative_path == 'deploy_logs':
            return True
        
        # تجاهل الملفات المخفية في المجلد الرئيسي (مثل .git, .env)
        parts = relative_path.split('/')
        if parts[0].startswith('.'):
            return True
            
        for pattern in self.ignored_patterns:
            if pattern.startswith('.'):
                continue
            if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(file_path.name, pattern):
                return True
                
        return False

    def get_file_hash(self, file_path):
        """حساب MD5 Hash للملف"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return None

    def get_all_files(self):
        """الحصول على جميع الملفات المحلية غير المستثناة"""
        files = []
        for file_path in self.project_root.rglob('*'):
            if file_path.is_file() and not self.is_ignored(file_path):
                files.append(file_path)
        return files

    def _create_ssh_connection(self):
        """إنشاء اتصال SSH مع خادم الإنتاج"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        connect_params = {
            'hostname': self.server_ip,
            'port': int(self.ssh_port),
            'username': self.username,
            'timeout': 30
        }
        
        if self.private_key:
            key_path = Path(self.private_key)
            if not key_path.is_absolute():
                project_key = self.project_root / self.private_key
                if project_key.exists():
                    key_path = project_key
                else:
                    home_key = Path.home() / '.ssh' / self.private_key
                    if home_key.exists():
                        key_path = home_key
            
            if key_path.exists():
                try:
                    pkey = None
                    key_types = [('RSA', paramiko.RSAKey)]
                    if hasattr(paramiko, 'DSSKey'):
                        key_types.append(('DSA', paramiko.DSSKey))
                    if hasattr(paramiko, 'ECDSAKey'):
                        key_types.append(('ECDSA', paramiko.ECDSAKey))
                    if hasattr(paramiko, 'Ed25519Key'):
                        key_types.append(('Ed25519', paramiko.Ed25519Key))
                        
                    last_error = None
                    for name, key_class in key_types:
                        try:
                            if self.ssh_key_passphrase:
                                pkey = key_class.from_private_key_file(str(key_path), password=self.ssh_key_passphrase)
                            else:
                                pkey = key_class.from_private_key_file(str(key_path))
                            break
                        except Exception as e:
                            last_error = str(e)
                            continue
                            
                    if pkey:
                        connect_params['pkey'] = pkey
                    else:
                        raise Exception(last_error or "فشل تحميل SSH Key")
                except Exception as e:
                    if self.ssh_password:
                        print(f"⚠️  فشل استخدام SSH Key: {e}. سيتم تجربة الباسورد...")
                        connect_params['password'] = self.ssh_password
                    else:
                        raise e
            elif self.ssh_password:
                connect_params['password'] = self.ssh_password
        elif self.ssh_password:
            connect_params['password'] = self.ssh_password
        else:
            raise Exception("لا توجد طريقة مصادقة صالحة في الإعدادات")
        try:
            ssh.connect(**connect_params)
        except Exception as e:
            if 'pkey' in connect_params and self.ssh_password:
                print(f"⚠️  فشل الاتصال بمفتاح SSH ({e}). سيتم المحاولة بكلمة المرور...")
                # Remove pkey and retry with password
                connect_params.pop('pkey', None)
                connect_params['password'] = self.ssh_password
                ssh.connect(**connect_params)
            else:
                raise e
        return ssh


    def test_connection(self):
        """اختبار الاتصال بالخادم"""
        print("🔍 اختبار الاتصال بالخادم...")
        if not PARAMIKO_AVAILABLE:
            print("❌ مكتبة paramiko غير مثبتة محلياً!")
            return False
            
        try:
            ssh = self._create_ssh_connection()
            ssh.close()
            print(f"✅ الاتصال بالخادم ناجح! ({self.username}@{self.server_ip})")
            return True
        except Exception as e:
            print(f"❌ فشل الاتصال بالخادم: {e}")
            return False

    def upload_with_smart_skip(self, files):
        """رفع الملفات ومقارنتها بالخادم، وتخطي أي ملف متطابق الحجم"""
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            total_files = len(files)
            uploaded = 0
            skipped = 0
            uploaded_files = []
            skipped_examples = []
            start_time = time.time()
            
            print(f"📤 بدء المزامنة والرفع الذكي...")
            
            for i, file_path in enumerate(files):
                if not file_path.exists():
                    skipped += 1
                    continue
                    
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                should_skip = False
                try:
                    remote_stat = sftp.stat(remote_file)
                    local_stat = file_path.stat()
                    if remote_stat.st_size == local_stat.st_size:
                        should_skip = True
                        skipped += 1
                        if len(skipped_examples) < 10:
                            skipped_examples.append(relative_path)
                except:
                    should_skip = False
                    
                # عرض شريط التقدم
                percentage = ((i + 1) / total_files) * 100
                elapsed = time.time() - start_time
                remaining = total_files - (i + 1)
                eta = int((elapsed / (i + 1)) * remaining) if i > 0 else 0
                eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                
                bar_length = 25
                filled_length = int(bar_length * (i + 1) // total_files)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                print(f"\r[{bar}] {percentage:.1f}% - مرفوع: {uploaded}, متخطى: {skipped} - متبقي: {eta_text}", end='', flush=True)
                
                if should_skip:
                    continue
                    
                try:
                    self._create_remote_directories(sftp, remote_file)
                    sftp.put(str(file_path), remote_file)
                    uploaded += 1
                    uploaded_files.append(relative_path)
                except Exception as e:
                    print(f"\n⚠️  خطأ في رفع {relative_path}: {e}")
                    
            print()
            sftp.close()
            ssh.close()
            
            print(f"✅ اكتمل الرفع الذكي في {time.time() - start_time:.1f}ث - تم رفع: {uploaded}، وتخطي: {skipped}")
            if uploaded_files:
                self._save_upload_log(uploaded_files, "رفع مع تخطي المطابق بالسيرفر")
            self.uploaded_files = uploaded_files
            return True
        except Exception as e:
            print(f"\n❌ خطأ أثناء الرفع الذكي: {e}")
            return False

    def upload_all_files(self, files):
        """رفع كافة الملفات واستبدالها على السيرفر بدون شروط"""
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            total_files = len(files)
            uploaded = 0
            uploaded_files = []
            start_time = time.time()
            
            print(f"📤 رفع كافة الملفات ({total_files})...")
            
            for i, file_path in enumerate(files):
                if not file_path.exists():
                    continue
                    
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                try:
                    self._create_remote_directories(sftp, remote_file)
                    sftp.put(str(file_path), remote_file)
                    uploaded += 1
                    uploaded_files.append(relative_path)
                except Exception as e:
                    print(f"\n⚠️  خطأ في رفع {relative_path}: {e}")
                    
                percentage = ((i + 1) / total_files) * 100
                elapsed = time.time() - start_time
                remaining = total_files - (i + 1)
                eta = int((elapsed / (i + 1)) * remaining) if i > 0 else 0
                eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                
                bar_length = 25
                filled_length = int(bar_length * (i + 1) // total_files)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                print(f"\r[{bar}] {percentage:.1f}% - مرفوع: {uploaded} - متبقي: {eta_text}", end='', flush=True)
                
            print()
            sftp.close()
            ssh.close()
            
            print(f"✅ تم رفع {uploaded} ملف بنجاح في {time.time() - start_time:.1f}ث")
            if uploaded_files:
                self._save_upload_log(uploaded_files, "رفع كافة الملفات بالكامل")
            self.uploaded_files = uploaded_files
            return True
        except Exception as e:
            print(f"\n❌ خطأ أثناء رفع كافة الملفات: {e}")
            return False

    def upload_modified_only(self, files):
        """رفع الملفات المعدلة فقط بمقارنة الـ MD5 Hashes محلياً (سريع جداً)"""
        print("🔍 فحص التغييرات محلياً بناءً على النشر السابق...")
        
        previous_hashes = {}
        if self.hash_file.exists():
            try:
                with open(self.hash_file, 'r', encoding='utf-8') as f:
                    previous_hashes = json.load(f)
            except:
                print("⚠️  تحذير: تعذر قراءة ملف hashes السابق.")
                
        modified_files = []
        new_files = []
        changed_files = []
        uploaded_files = []
        
        for file_path in files:
            if not file_path.exists():
                continue
                
            relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
            current_hash = self.get_file_hash(file_path)
            
            if relative_path not in previous_hashes:
                modified_files.append(file_path)
                new_files.append(relative_path)
            elif previous_hashes[relative_path] != current_hash:
                modified_files.append(file_path)
                changed_files.append(relative_path)
                
        if not modified_files:
            print("✅ جميع الملفات متطابقة ومحدثة بالكامل مع آخر نشر محلي!")
            return True
            
        print(f"📊 تم اكتشاف: {len(new_files)} ملف جديد، {len(changed_files)} ملف معدل.")
        
        # عرض بعض الملفات المكتشفة للتأكيد
        if new_files:
            print("📄 ملفات جديدة:")
            for f in new_files[:5]:
                print(f"   + {f}")
            if len(new_files) > 5:
                print(f"   ... و {len(new_files) - 5} ملف جديد آخر")
        if changed_files:
            print("📝 ملفات معدلة:")
            for f in changed_files[:5]:
                print(f"   ~ {f}")
            if len(changed_files) > 5:
                print(f"   ... و {len(changed_files) - 5} ملف معدل آخر")
                
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            total_files = len(modified_files)
            uploaded = 0
            start_time = time.time()
            
            print(f"📤 رفع {total_files} ملف معدل...")
            
            for i, file_path in enumerate(modified_files):
                if not file_path.exists():
                    continue
                    
                relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
                remote_file = f"{self.remote_path}/{relative_path}"
                
                try:
                    self._create_remote_directories(sftp, remote_file)
                    sftp.put(str(file_path), remote_file)
                    uploaded += 1
                    uploaded_files.append(relative_path)
                except Exception as e:
                    print(f"\n⚠️  خطأ في رفع {relative_path}: {e}")
                    
                percentage = ((i + 1) / total_files) * 100
                elapsed = time.time() - start_time
                remaining = total_files - (i + 1)
                eta = int((elapsed / (i + 1)) * remaining) if i > 0 else 0
                eta_text = f"{eta}ث" if eta < 60 else f"{eta//60}د"
                
                bar_length = 25
                filled_length = int(bar_length * (i + 1) // total_files)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                print(f"\r[{bar}] {percentage:.1f}% - مرفوع: {uploaded} - متبقي: {eta_text}", end='', flush=True)
                
            print()
            sftp.close()
            ssh.close()
            
            print(f"✅ اكتمل الرفع في {time.time() - start_time:.1f}ث. تم رفع {uploaded} ملف.")
            if uploaded_files:
                self._save_upload_log(uploaded_files, "رفع الملفات المعدلة محلياً فقط")
            self.uploaded_files = uploaded_files
            return True
        except Exception as e:
            print(f"\n❌ خطأ أثناء الرفع: {e}")
            return False

    def deploy_single_file(self, filename):
        """رفع ملف واحد محدد بالاسم"""
        print(f"\n🔄 رفع ملف واحد محدد: {filename}")
        file_path = self.project_root / filename
        if not file_path.exists():
            print(f"❌ خطأ: الملف غير موجود محلياً: {filename}")
            return False
            
        if self.is_ignored(file_path):
            print(f"❌ خطأ: الملف المحدد مستثنى ومحمي من النشر: {filename}")
            return False
            
        if not self.test_connection():
            return False
            
        try:
            ssh = self._create_ssh_connection()
            sftp = ssh.open_sftp()
            
            relative_path = file_path.relative_to(self.project_root)
            remote_file = f"{self.remote_path}/{relative_path}".replace('\\', '/')
            
            self._create_remote_directories(sftp, remote_file)
            print(f"📤 رفع الملف إلى {remote_file}...")
            sftp.put(str(file_path), remote_file)
            
            sftp.close()
            ssh.close()
            print("✅ تم رفع الملف بنجاح!")
            
            # تحديث الـ hash للملف الفردي
            previous_hashes = {}
            if self.hash_file.exists():
                try:
                    with open(self.hash_file, 'r', encoding='utf-8') as f:
                        previous_hashes = json.load(f)
                except:
                    pass
            
            relative_path_str = str(relative_path).replace('\\', '/')
            previous_hashes[relative_path_str] = self.get_file_hash(file_path)
            with open(self.hash_file, 'w', encoding='utf-8') as f:
                json.dump(previous_hashes, f, indent=2, ensure_ascii=False)
                
            self.uploaded_files = [relative_path_str]
            self.run_post_deploy_commands(first_deploy=False)
            return True
        except Exception as e:
            print(f"❌ خطأ في رفع الملف الفردي: {e}")
            return False

    def execute_remote_command(self, ssh, cmd, label):
        """تشغيل أمر بعيد بأمان، مع معالجة إيقاف الـ Shell Access"""
        print(f"  ⏳ {label}...")
        try:
            stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            
            combined = (out + "\n" + err).strip()
            if "Shell access is not enabled" in combined or "not enabled on your account" in combined:
                print(f"  ⚠️  تنبيه: لا يوجد صلاحية تشغيل أوامر (Shell Access) على هذا السيرفر.")
                return False, "NO_SHELL"
                
            if exit_code == 0:
                print(f"  ✅ {label} - نجح")
                return True, out
            else:
                print(f"  ❌ {label} - فشل")
                if err:
                    print(f"     خطأ: {err[-200:]}")
                return False, err
        except Exception as e:
            print(f"  ❌ {label} - خطأ اتصال: {e}")
            return False, str(e)

    def run_post_deploy_commands(self, first_deploy=False):
        """تنفيذ المهام ما بعد الرفع (Migrations / Collectstatic / Passenger Restart)"""
        remote_app_name = Path(self.remote_path).name
        
        # تجهيز مسارات البيئة الافتراضية
        venv = f"/home/{self.username}/virtualenv/{remote_app_name}/{self.python_version}/bin/python"
        manage = f"{self.remote_path}/manage.py"
        pip = f"/home/{self.username}/virtualenv/{remote_app_name}/{self.python_version}/bin/pip"
        
        # الكشف الذكي للتغييرات
        run_pip = False
        run_migrate = False
        run_collectstatic = False
        
        uploaded_list = getattr(self, 'uploaded_files', []) or []
        for file_path in uploaded_list:
            file_name = str(file_path).lower().replace('\\', '/')
            if 'requirements.txt' in file_name:
                run_pip = True
            if '/migrations/' in file_name and file_name.endswith('.py') and not file_name.endswith('__init__.py'):
                run_migrate = True
            if 'static/' in file_name:
                run_collectstatic = True
                
        # تحضير الأوامر
        exec_commands = []
        if run_pip or first_deploy:
            exec_commands.append((f"{pip} install -r {self.remote_path}/requirements.txt", "تثبيت المتطلبات (pip install)"))
        if run_migrate or first_deploy:
            exec_commands.append((f"{venv} {manage} migrate --noinput", "تحديث قاعدة البيانات (migrate)"))
        if run_collectstatic or first_deploy:
            exec_commands.append((f"{venv} {manage} collectstatic --noinput", "تجميع الملفات الثابتة (collectstatic)"))
            
        # فتح اتصال لتنفيذ الأوامر ولمس ملفات الريستارت
        try:
            ssh = self._create_ssh_connection()
            
            if exec_commands:
                print("\n⚙️  تنفيذ أوامر التحديث على السيرفر...")
                for cmd, label in exec_commands:
                    success, output = self.execute_remote_command(ssh, cmd, label)
                    if output == "NO_SHELL":
                        # إذا كان السيرفر مقفول فيه الـ shell، نوقف محاولة تشغيل باقي الأوامر
                        print("  💡 يرجى تشغيل الميجريشن والستاتيك يدوياً إذا لزم الأمر.")
                        break
            else:
                print("\n🔍 لم يتم الكشف عن تغييرات في المتطلبات أو الميجريشن. تخطي الأوامر.")
                
            # عمل ريستارت للتطبيق (دائماً يتم بالـ SFTP لضمان عمله في كل الحالات)
            print("\n🔄 تحديث ملفات ريستارت تطبيق الويب (Restart Passenger)...")
            try:
                sftp = ssh.open_sftp()
                sftp_touch(sftp, f"{self.remote_path}/tmp/restart.txt")
                sftp_touch(sftp, f"{self.remote_path}/passenger_wsgi.py")
                sftp.close()
            except Exception as e:
                print(f"  ⚠️  تعذر تحديث ملفات الريستارت بالـ SFTP: {e}")
                
            ssh.close()
        except Exception as e:
            print(f"⚠️  تعذر إتمام أوامر ما بعد النشر: {e}")

    def sync_all(self):
        """مزامنة كاملة مع تخطي المتطابق"""
        print("\n🔄 مزامنة كاملة مع الخادم...")
        if not self.test_connection():
            return False
            
        files = self.get_all_files()
        print(f"📊 إجمالي الملفات المحلية للفحص: {len(files)}")
        
        confirm = input("❓ هل تريد البدء في الرفع الذكي للملفات؟ (y/N): ").lower()
        if confirm != 'y':
            print("❌ تم إلغاء العملية.")
            return False
            
        success = self.upload_with_smart_skip(files)
        if success:
            self._save_current_hashes(files)
            self.run_post_deploy_commands(first_deploy=False)
        return success

    def deploy_modified(self):
        """طريقة النشر التفاعلية مع خيارات متعددة"""
        if not self.test_connection():
            return False
            
        all_files = self.get_all_files()
        print(f"📊 تم إحصاء {len(all_files)} ملف محلي مؤهل للنشر.")
        
        print("\n📋 اختر طريقة النشر المفضلة:")
        print("1️⃣  رفع كامل مع استبدال (يرفع كل شيء - بطيء)")
        print("2️⃣  رفع كامل ذكي مع تخطي المطابق (يقارن الأحجام بالسيرفر - متوسط)")
        print("3️⃣  رفع الملفات المعدلة محلياً فقط (يقارن hashes محلياً - سريع جداً ⚡)")
        print("❌ أي رقم آخر للإلغاء")
        
        choice = input("\n❓ اختيارك (1/2/3): ").strip()
        
        success = False
        method_name = ""
        
        if choice == "1":
            confirm = input(f"❓ هل أنت متأكد من رفع واستبدال {len(all_files)} ملف بالكامل؟ (y/N): ").lower()
            if confirm == 'y':
                success = self.upload_all_files(all_files)
                method_name = "رفع كامل واستبدال"
        elif choice == "2":
            success = self.upload_with_smart_skip(all_files)
            method_name = "رفع كامل ذكي مع تخطي المطابق"
        elif choice == "3":
            success = self.upload_modified_only(all_files)
            method_name = "رفع المعدل محلياً فقط"
        else:
            print("❌ تم الإلغاء.")
            return False
            
        if success:
            self._save_current_hashes(all_files)
            self.run_post_deploy_commands(first_deploy=not self.hash_file.exists())
            print(f"\n🎉 تم النشر بنجاح! [{method_name}]")
            
        return success

    def _save_current_hashes(self, files):
        """حفظ hashes الملفات الحالية محلياً"""
        current_hashes = {}
        for file_path in files:
            relative_path = str(file_path.relative_to(self.project_root)).replace('\\', '/')
            current_hashes[relative_path] = self.get_file_hash(file_path)
            
        try:
            with open(self.hash_file, 'w', encoding='utf-8') as f:
                json.dump(current_hashes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  تحذير: لم نتمكن من حفظ ملف hashes محلياً: {e}")

    def _create_remote_directories(self, sftp, remote_file):
        """إنشاء مجلدات المسار البعيد إذا لم تكن موجودة"""
        remote_dir = '/'.join(remote_file.split('/')[:-1])
        if remote_dir != self.remote_path:
            path_parts = remote_dir.replace(self.remote_path + '/', '').split('/')
            current_path = self.remote_path
            for part in path_parts:
                if part:
                    current_path = f"{current_path}/{part}"
                    try:
                        sftp.mkdir(current_path)
                    except:
                        pass

    def _save_upload_log(self, uploaded_files, method_name):
        """حفظ سجل بالملفات المرفوعة للرجوع إليها"""
        try:
            from datetime import datetime
            log_dir = self.project_root / "deploy_logs"
            log_dir.mkdir(exist_ok=True)
            
            log_file = log_dir / f"upload_{self.site}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"📤 تقرير النشر للموقع: {self.site.upper()} ({method_name})\n")
                f.write(f"⏰ التوقيت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"🖥️  الخادم: {self.server_ip}\n")
                f.write(f"📊 عدد الملفات: {len(uploaded_files)}\n")
                f.write("=" * 60 + "\n\n")
                for i, file_path in enumerate(uploaded_files, 1):
                    f.write(f"{i:4d}. {file_path}\n")
            
            print(f"📝 تم حفظ تفاصيل النشر في السجل: {log_file.name}")
            
            # الإبقاء على آخر 10 ملفات لوج فقط وحذف القديم
            all_logs = sorted(log_dir.glob(f"upload_{self.site}_*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
            for old_log in all_logs[10:]:
                old_log.unlink()
        except Exception as e:
            print(f"⚠️  تحذير: تعذر كتابة ملف السجل (Log): {e}")


def main():
    parser = argparse.ArgumentParser(description="سكريبت النشر التفاعلي للمجلة العلمية")
    parser.add_argument('--site', choices=['ar', 'en'], help='الموقع المراد النشر إليه (ar أو en)')
    parser.add_argument('--mode', choices=['all', 'modified', 'file', 'sync', 'test'], help='وضع النشر')
    parser.add_argument('--file', type=str, help='اسم ملف محدد لرفعه بشكل منفرد')
    args = parser.parse_args()
    
    # 1. تحديد الموقع (تفاعلي لو مش محدد)
    site = args.site
    if not site:
        print("\n📋 اختر الموقع المراد النشر إليه:")
        print("1️⃣  الموقع العربي (ar)")
        print("2️⃣  الموقع الإنجليزي (en)")
        
        while site not in ["ar", "en"]:
            try:
                choice = input("\n❓ اختيارك (1/2): ").strip()
                if choice == "1":
                    site = "ar"
                elif choice == "2":
                    site = "en"
                elif choice.lower() in ["ar", "en"]:
                    site = choice.lower()
                else:
                    print("⚠️  اختيار غير صحيح. يرجى كتابة 1 أو 2.")
            except KeyboardInterrupt:
                print("\n❌ تم الإلغاء.")
                sys.exit(0)
                
    try:
        manager = DeploymentManager(site)
        
        # 2. تحديد الوضع وتشغيل العملية المناسبة
        mode = args.mode
        if not mode:
            if args.file:
                mode = 'file'
            else:
                mode = 'modified' # الافتراضي التفاعلي
                
        if mode == 'test':
            manager.test_connection()
        elif mode == 'file':
            if not args.file:
                filename = input("❓ اكتب مسار واسم الملف المراد رفعه (مثال: apps/publishing/models.py): ").strip()
            else:
                filename = args.file
            manager.deploy_single_file(filename)
        elif mode == 'sync':
            manager.sync_all()
        elif mode == 'all':
            files = manager.get_all_files()
            manager.upload_all_files(files)
        elif mode == 'modified':
            manager.deploy_modified()
            
    except KeyboardInterrupt:
        print("\n❌ تم إيقاف العملية.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
