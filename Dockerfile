FROM python

WORKDIR /app
COPY requirements.txt /app
RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt
COPY ./ /app/
EXPOSE 8080
CMD python app.py
