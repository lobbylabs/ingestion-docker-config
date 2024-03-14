FROM selenium/standalone-chrome

USER root
RUN wget https://bootstrap.pypa.io/get-pip.py
RUN python3 get-pip.py
RUN python3 -m pip install selenium

WORKDIR /app


COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .