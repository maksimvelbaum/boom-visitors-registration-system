# boom-visitors-registration-system
[[Creator Website]](https://velbaum.cc) [[Buy me a coffee]](https://buymeacoffee.com/maksim_velbaum)

Very simple visitors registration system, it have front-end and database, small logs in front end but if you need to get full log, you will need to use some BI tool,  like Redash, Superset or other.

## Setup

Install Docker and Docker Compose 

**Tested on  Docker version 28.3.2, build 578ccf6 and Docker compose V2 , OS Debian 12**

```bash
git clone https://github.com/maksimvelbaum/boom-visitors-registration-system.git
```

```bash
cd visitors-registration-system
```

```bash
nano app.py
```

**Edit rows** 

21-24  SMTP Settings

150-154 PDF Pass text

163  email text 

**Save file** 
```bash
sudo docker-compose up
```
**Ckeck logs, if all working  Ctrl+C**

```bash
sudo docker-compose up -d
```

**Application will work on port 8550**

```bash
your-ip-adress:8550
```


