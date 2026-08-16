<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

class PushSimpleIndex extends Migration
{
    public function up()
    {
        Schema::table('users', function (Blueprint $table) {
            $table->index('email');
        });
    }

    public function down()
    {
    }
}
