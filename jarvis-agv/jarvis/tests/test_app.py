import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jarvis import app
from jarvis import school

ROWS = [
 {'id':1,'dia':0,'inicio':'07:30:00','fim':'08:20:00','professor':'Ana Silva','materia':'Português','turma':'1A','sala':'04'},
 {'id':2,'dia':0,'inicio':'08:20:00','fim':'09:10:00','professor':'Ana Silva','materia':'Português','turma':'2B','sala':'07'},
 {'id':3,'dia':0,'inicio':'07:30:00','fim':'08:20:00','professor':'Carlos Souza','materia':'Matemática','turma':'2B','sala':'07'}]

class Tests(unittest.TestCase):
 def query(self,q):
  with patch.object(school,'schedule_rows',return_value=ROWS):return school.school_answer(q,datetime(2026,10,5,7,45))
 def test_teacher(self):
  answer=self.query('Onde está a professora Ana Silva segunda às 07:45?')
  self.assertIn('turma 1A',answer);self.assertNotIn('Carlos',answer);self.assertNotIn('2B',answer)
 def test_boundary(self):
  answer=self.query('Onde está a professora Ana Silva segunda às 08:20?')
  self.assertIn('turma 2B',answer);self.assertNotIn('turma 1A',answer)
 def test_class(self):self.assertNotIn('Ana Silva',self.query('Quais aulas da turma 2B segunda às 07:45?'))
 def test_room(self):
  answer=self.query('Quais aulas na sala 04 segunda?')
  self.assertIn('Ana Silva',answer);self.assertNotIn('Carlos',answer)
 def test_ambiguous_teacher(self):
  with patch.object(school,'schedule_rows',return_value=ROWS+[dict(ROWS[0],professor='Ana Costa')]):
   self.assertIn('Qual professor',school.school_answer('Onde está a professora Ana?',datetime(2026,10,5,7,45)))
 def test_unknown(self):self.assertIn('Não encontrei',self.query('Onde está o professor Marcos segunda?'))
 def test_interval_normalizes_unpadded_clock(self):
  rows=[dict(ROWS[0],inicio='7:45',fim='8:35')]
  with patch.object(school,'schedule_rows',return_value=rows):
   answer=school.school_answer('Quais aulas de terça-feira das 7:45 às 8:35?',datetime(2026,10,5,7,45))
  self.assertIn('07:45–08:35',answer);self.assertIn('Ana Silva',answer)
 def test_empty_day_is_distinct_from_empty_filter(self):
  with patch.object(school,'schedule_rows',return_value=[]):
   answer=school.school_answer('Quais aulas hoje?',datetime(2026,10,5,7,45))
  self.assertIn('na planilha',answer)
  with patch.object(school,'schedule_rows',return_value=ROWS):
   answer=school.school_answer('Quais aulas da turma 9Z segunda?',datetime(2026,10,5,7,45))
  self.assertIn('Não encontrei',answer)
 def test_model_general(self):self.assertIsNone(school.school_answer('Explique fotossíntese.'))
 def test_http(self):
  from email.message import Message
  def req(path, data=None):
   handler=app.Handler.__new__(app.Handler)
   handler.path=path;handler.command='GET' if data is None else 'POST'
   handler.request_version='HTTP/1.1';handler.requestline=handler.command+' '+path+' HTTP/1.1'
   handler.client_address=('127.0.0.1',0);handler.log_message=lambda *args:None
   body=b'' if data is None else json.dumps(data).encode()
   handler.rfile=io.BytesIO(body);handler.wfile=io.BytesIO();handler.headers=Message()
   handler.headers['Content-Type']='application/json';handler.headers['Content-Length']=str(len(body))
   handler.headers['Host']='localhost:8000'
   (handler.do_GET if data is None else handler.do_POST)()
   return handler.wfile.getvalue()
  async def audio(*args):return b'ID3sample'
  with patch.object(app.voice,'synthesize',side_effect=audio):
   self.assertTrue(req('/api/tts',{'texto':'Olá','voz':'antonio','velocidade':1.15}).endswith(b'ID3sample'))
  self.assertIn(b'404',req('/config.json').split(b'\r\n')[0])
  self.assertIn(b'200',req('/speech.js').split(b'\r\n')[0])
  with patch.object(app,'open_model',return_value=io.BytesIO(b'{"message":{"content":"Ola."},"done":true}\n')):
   self.assertIn(b'"texto": "Ola."',req('/api/chat',{'mensagem':'Oi'}))

if __name__=='__main__':unittest.main()
